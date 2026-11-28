"""Tune and evaluate one view at a time in shuffled four-view rounds."""

from collections.abc import Callable
from copy import deepcopy
import json
import logging
from random import shuffle
from time import sleep
from uuid import uuid4

from ax3l.activity.ViewConfiguration import (
    apply_values, editable_parameters, historical_values, other_parameters, parameter_comparison,
)
from ax3l.app.experiment.ConfigurationLog import ConfigurationLog
from ax3l.interface.database.DbMgr import DbMgr
from ax3l.interface.database.EventLogDb import EventLogDb
from ax3l.interface.database.ExperimentDb import ExperimentDb
from ax3l.constants.DAx3l import DAx3l
from ax3l.constants.DEventCategory import DEventCategory as Events
from ax3l.constants.DSnakeLab import DSnakeLab
from ax3l.entities.ExperimentState import ExperimentState
from ax3l.entities.ExperimentView import VIEWS
from ax3l.entities.ViewHistory import ViewHistory
from ax3l.entities.ViewProposal import ViewProposal
from ax3l.interface.LLM import LLM, LLMTimeoutError
from ax3l.interface.SimulationConfiguration import SimulationConfiguration
from ax3l.interface.SnakeLab import SnakeLab
from ax3l.interface.ViewConversation import ViewConversation
from ax3l.presentation.ViewPrompts import ViewPrompts


class ExperimentLoop:
    def __init__(self, db: DbMgr, llm: LLM, snake: SnakeLab):
        self._snake = snake
        self._store = ExperimentDb(db)
        self._events = EventLogDb(db)
        self._configuration_log = ConfigurationLog(self._events)
        self._conversation = ViewConversation(llm, self._events)
        self._prompts = ViewPrompts()

    def run(self, *, cycles: int | None = None, check: Callable[[], None] = lambda: None) -> None:
        state = self._store.load()
        if state is None:
            while self._snake.is_simulation_running():
                check()
                sleep(DSnakeLab.STATUS_POLL_SECONDS)
            state = self._initialize()
        completed = 0
        while cycles is None or completed < cycles:
            check()
            if state.phase == "completed":
                state = self._next_cycle(state)
            elif state.phase in ("choosing", "revising", "evaluating"):
                try:
                    if state.phase == "evaluating":
                        self._evaluate_view(state)
                        completed += 1
                    else:
                        self._choose_view(state)
                except LLMTimeoutError:
                    logging.warning("LLM timed out while %s %s; restarting the conversation "
                                    "with its original prompt in %s seconds.",
                                    state.phase, state.view_name, DAx3l.LLM_TIMEOUT_RETRY_SECONDS)
                    sleep(DAx3l.LLM_TIMEOUT_RETRY_SECONDS)
            elif state.phase == "ready":
                state.preceding_match = self._snake.find_config_run(state.config)
                if state.preceding_match and not (state.baseline or state.seed_baseline):
                    state.phase = "revising"
                    self._store.save(state)
                    continue
                state.phase = "submitting"
                self._store.save(state)
                state.run_id = self._snake.submit_simulation(state.config)
                state.phase = "running"
                self._store.save(state)
            elif state.phase == "submitting":
                match = self._snake.find_config_run(state.config)
                if match is None or match == state.preceding_match:
                    raise RuntimeError("Simulation submission is unresolved; it will not be retried automatically.")
                state.run_id, state.phase = match, "running"
                self._store.save(state)
            elif state.phase == "running":
                self._record_submission(state)
                status = self._snake.get_simulation_status(state.run_id)
                if status == "completed":
                    if Events.SnakeLab.COMPLETED not in self._store.run_events(state.run_id):
                        self._events.log(Events.SnakeLab.COMPLETED, Events.SnakeLab.CATEGORY, "INFO",
                                         "Simulation completed.", process_id=state.run_id)
                    state.phase = "comparing"
                    self._store.save(state)
                elif status in ("failed", "cancelled"):
                    self._events.log(Events.SnakeLab.TERMINAL_EVENTS[status], Events.SnakeLab.CATEGORY, "ERROR",
                                     f"Simulation {status}.", process_id=state.run_id)
                    raise RuntimeError(f"Simulation {state.run_id} {status}; no completed result to compare.")
                else:
                    if status == "running" and Events.SnakeLab.STARTED not in self._store.run_events(state.run_id):
                        self._events.log(Events.SnakeLab.STARTED, Events.SnakeLab.CATEGORY, "INFO",
                                         "Simulation started running.", process_id=state.run_id)
                    sleep(DSnakeLab.STATUS_POLL_SECONDS)
            elif state.phase == "comparing":
                self._finish(state)
            else:
                raise ValueError(f"Unknown experiment phase: {state.phase}")

    def _initialize(self) -> ExperimentState:
        golden = self._events.current_golden_config()
        run_id = golden["process_id"] if golden else None
        config = self._completed_result(run_id)["config"] if run_id else SimulationConfiguration.defaults()
        state = ExperimentState(str(uuid4()), "completed" if run_id else "ready", deepcopy(config),
                                baseline=True, golden_run_id=run_id, latest_run_id=run_id,
                                reference_run_id=run_id)
        self._store.save(state)
        return state

    def _completed_result(self, run_id: str) -> dict:
        result = self._snake.get_run_result(run_id)
        if result is None or result["status"] != "completed" or result["high_score"] is None:
            raise ValueError(f"Simulation {run_id} needs a completed result with a high score.")
        return result

    def _next_cycle(self, previous: ExperimentState) -> ExperimentState:
        order = previous.order.copy()
        index = previous.view_index
        if not (previous.baseline or previous.seed_baseline):
            index += 1
        if not order or index == len(order):
            order = list(VIEWS)
            shuffle(order)
            index = 0
        config = deepcopy(self._completed_result(previous.golden_run_id)["config"])
        rotate = previous.failures >= DAx3l.SEED_ROTATION_FAILURES
        if rotate:
            config["seed"] += 1
        state = ExperimentState(
            str(uuid4()), "ready" if rotate else "choosing", config,
            seed_baseline=rotate, golden_run_id=previous.golden_run_id,
            reference_run_id=previous.golden_run_id, latest_run_id=previous.golden_run_id,
            order=order, view_index=index, failures=previous.failures,
            golden_history=previous.golden_history,
        )
        self._store.save(state)
        return state

    def _result_context(self, name: str, reference_id: str, latest_id: str | None = None) -> dict:
        episodes = {"architecture": self._snake.get_episode_scores,
                    "exploration": self._snake.get_exploration_episodes,
                    "reward-signals": self._snake.get_reward_episodes,
                    "training": self._snake.get_training_episodes}[name]
        reference = self._completed_result(reference_id)
        context = dict(reference_run_id=reference_id, reference_episodes=episodes(reference_id),
                       reference_high_score=reference["high_score"], reference_config=reference["config"])
        if latest_id is not None:
            context.update(latest_run_id=latest_id, latest_episodes=episodes(latest_id),
                           latest_high_score=self._completed_result(latest_id)["high_score"])
        return context

    def _evaluate_view(self, state: ExperimentState) -> None:
        name = state.view_name
        proposal = state.proposals[name]
        context = self._result_context(name, state.reference_run_id, state.latest_run_id)
        context.update(previous_hypothesis=proposal.hypothesis,
                       previous_values=parameter_comparison(context["reference_config"], proposal.values))
        content = self._prompts.render_evaluation(VIEWS[name], context)
        observation = self._conversation.evaluate(VIEWS[name], content, state.experiment_id)
        state.observations[name] = observation
        if state.latest_run_id == state.golden_run_id:
            state.golden_history = ViewHistory(name, proposal, state.reference_run_id,
                                              state.latest_run_id, observation)
        state.phase = "completed"
        self._store.save(state)

    def _choose_view(self, state: ExperimentState) -> None:
        name = state.view_name
        view = VIEWS[name]
        revising = state.phase == "revising"
        history = state.golden_history
        no_history = history is None or history.view != name
        context = self._result_context(name, state.golden_run_id) if no_history else self._result_context(
            name, history.reference_run_id, history.latest_run_id)
        if not no_history:
            context.update(previous_hypothesis=history.proposal.hypothesis,
                           previous_values=parameter_comparison(context["reference_config"], history.proposal.values),
                           previous_observations=history.observations)
        if revising:
            proposal = state.proposals[name]
            context.update(rejected_hypothesis=proposal.hypothesis, rejected_values=proposal.values)
        context.update(parameters=editable_parameters(view, state.config),
                       other_parameters=other_parameters(view, state.config),
                       historical_simulation_data=historical_values(
                           view, self._snake.get_scored_runs(state.config["seed"])))
        prompt = self._prompts.render(view, context, no_history=no_history, duplicate=revising)
        proposal = self._conversation.propose(view, prompt, state.experiment_id)
        if revising:
            proposal = ViewProposal(proposal.hypothesis, {**state.proposals[name].values, **proposal.values})
        state.config = apply_values(state.config, proposal.values)
        state.proposals[name] = proposal
        state.phase = "ready"
        self._store.save(state)

    def _record_submission(self, state: ExperimentState) -> None:
        recorded = self._store.run_events(state.run_id)
        parent = recorded.get(Events.Configuration.PROPOSAL_ACCEPTED)
        if not state.baseline and not state.seed_baseline and parent is None:
            parent = self._events.log(Events.Configuration.PROPOSAL_ACCEPTED, Events.Configuration.CATEGORY, "INFO",
                                     json.dumps(dict(draft_id=state.experiment_id, config=state.config,
                                                     origin="llm", view=state.view_name), allow_nan=False),
                                     process_id=state.run_id)
        if Events.SnakeLab.SUBMITTED not in recorded:
            description = ("Submitted baseline configuration." if state.baseline else
                           "Submitted golden configuration with a new seed." if state.seed_baseline else
                           f"Submitted {state.view_name} configuration.")
            self._events.log(Events.SnakeLab.SUBMITTED, Events.SnakeLab.CATEGORY, "INFO", description,
                             process_id=state.run_id, parent_event_id=parent, ax3l_version=DAx3l.VERSION)

    def _promote(self, run_id: str, reason: str) -> None:
        result = self._completed_result(run_id)
        self._configuration_log.golden_config_created(
            run_id, reason=reason, experiment_score=dict(simulations=self._snake.get_num_sims(),
                                                        score=result["high_score"], seed=result["config"]["seed"]))

    def _finish(self, state: ExperimentState) -> None:
        self._record_submission(state)
        latest = self._completed_result(state.run_id)
        if state.baseline or state.seed_baseline:
            winner = state.run_id
            reason = (f"Established the golden baseline on seed {latest['config']['seed']}."
                      if state.seed_baseline else "Established the default configuration baseline.")
            failures = 0
        else:
            comparison = self._store.comparison(state.run_id)
            if comparison is None:
                golden = self._completed_result(state.golden_run_id)
                won = latest["high_score"] >= golden["high_score"]
                winner = state.run_id if won else state.golden_run_id
                reason = f"High score: {latest['high_score']} {'>=' if won else '<'} {golden['high_score']}."
                comparison = dict(golden_run_id=state.golden_run_id, latest_run_id=state.run_id,
                                  current_golden_run_id=winner, reason=reason,
                                  failures=0 if won else state.failures + 1)
                self._events.log(Events.Configuration.COMPARED, Events.Configuration.CATEGORY, "INFO",
                                 json.dumps(comparison), process_id=state.run_id)
            winner, reason, failures = (comparison["current_golden_run_id"], comparison["reason"],
                                        comparison["failures"])
        current = self._events.current_golden_config()
        if current is None or current["process_id"] != winner:
            self._promote(winner, reason)
        if winner == state.run_id:
            state.golden_history = None
        state.failures = failures
        state.reference_run_id = state.run_id if state.baseline or state.seed_baseline else state.golden_run_id
        state.golden_run_id, state.latest_run_id = winner, state.run_id
        state.phase = "completed" if state.baseline or state.seed_baseline else "evaluating"
        self._store.save(state)
