"""Evaluate results in four conversations before assembling four new proposals."""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
import json
from random import choice, shuffle
from time import sleep
from uuid import uuid4

from ax3l.activity.ViewConfiguration import apply_values, editable_parameters, other_parameters, view_values
from ax3l.app.experiment.ConfigurationLog import ConfigurationLog
from ax3l.interface.database.DbMgr import DbMgr
from ax3l.interface.database.EventLogDb import EventLogDb
from ax3l.interface.database.ExperimentDb import ExperimentDb
from ax3l.constants.DAx3l import DAx3l
from ax3l.constants.DEventCategory import DEventCategory as Events
from ax3l.constants.DSnakeLab import DSnakeLab
from ax3l.constants.DViewConversation import DViewConversation
from ax3l.entities.ExperimentState import ExperimentState
from ax3l.entities.ExperimentView import VIEWS
from ax3l.entities.ViewProposal import ViewProposal
from ax3l.interface.LLM import LLM
from ax3l.interface.SimulationConfiguration import SimulationConfiguration
from ax3l.interface.SnakeLab import SnakeLab
from ax3l.interface.SyntheticExperimentConfiguration import SyntheticExperimentConfiguration
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
            elif state.phase in ("choosing", "revising"):
                self._choose_view(state)
            elif state.phase == "ready":
                config = self._simulation_config(state)
                state.preceding_match = self._snake.find_config_run(config)
                if state.preceding_match and not (state.baseline or state.seed_baseline):
                    state.revision_view = choice(list(VIEWS))
                    state.phase = "revising"
                    self._store.save(state)
                    continue
                state.phase = "submitting"
                self._store.save(state)
                state.run_id = self._snake.submit_simulation(config)
                state.phase = "running"
                self._store.save(state)
            elif state.phase == "submitting":
                match = self._snake.find_config_run(self._simulation_config(state))
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
            elif state.phase == "evaluating":
                self._evaluate_view(state)
                if state.phase == "completed" and not state.baseline and not state.synthetic and state.proposals:
                    completed += 1
            else:
                raise ValueError(f"Unknown experiment phase: {state.phase}")

    def _initialize(self) -> ExperimentState:
        golden = self._events.current_golden_config()
        run_id = golden["process_id"] if golden else None
        config = self._completed_result(run_id)["config"] if run_id else SimulationConfiguration.defaults()
        initial = SyntheticExperimentConfiguration.load()
        previous = {name: ViewProposal(initial[name].hypothesis, view_values(view, config))
                    for name, view in VIEWS.items()} if run_id else {}
        state = ExperimentState(str(uuid4()), "evaluating" if run_id else "ready", deepcopy(config),
                                baseline=run_id is None, golden_run_id=run_id, latest_run_id=run_id,
                                reference_run_id=run_id, previous=previous,
                                synthetic=run_id is None, proposals=initial if run_id is None else {})
        self._store.save(state)
        return state

    def _completed_result(self, run_id: str) -> dict:
        result = self._snake.get_run_result(run_id)
        if result is None or result["status"] != "completed" or result["high_score"] is None:
            raise ValueError(f"Simulation {run_id} needs a completed result with a high score.")
        return result

    def _next_cycle(self, previous: ExperimentState) -> ExperimentState:
        order = list(VIEWS)
        shuffle(order)
        config = deepcopy(self._completed_result(previous.golden_run_id)["config"])
        state = ExperimentState(
            str(uuid4()), "choosing", config, golden_run_id=previous.golden_run_id,
            latest_run_id=previous.latest_run_id, reference_run_id=previous.reference_run_id, order=order,
            previous=previous.proposals or previous.previous,
            previous_seeded=previous.synthetic or not bool(previous.proposals),
            observations=previous.observations.copy(),
        )
        self._store.save(state)
        return state

    def _evaluate_view(self, state: ExperimentState) -> None:
        name = list(VIEWS)[len(state.observations)]
        view = VIEWS[name]
        proposals = state.proposals or state.previous
        previous = proposals[name]
        context = dict(previous_hypothesis=previous.hypothesis, previous_values=previous.values,
                       reference_run_id=state.reference_run_id, latest_run_id=state.latest_run_id)
        episodes = {"architecture": self._snake.get_episode_scores,
                    "exploration": self._snake.get_exploration_episodes,
                    "reward-signals": self._snake.get_reward_episodes,
                    "training": self._snake.get_training_episodes}[name]
        reference = episodes(state.reference_run_id)
        latest = reference if state.latest_run_id == state.reference_run_id else episodes(state.latest_run_id)
        reference_score = self._completed_result(state.reference_run_id)["high_score"]
        latest_score = (reference_score if state.latest_run_id == state.reference_run_id
                        else self._completed_result(state.latest_run_id)["high_score"])
        context.update(reference_episodes=reference, latest_episodes=latest,
                       reference_high_score=reference_score, latest_high_score=latest_score)
        content = self._prompts.render_evaluation(view, context)
        state.observations[name] = self._conversation.evaluate(view, content, state.experiment_id)
        if len(state.observations) == len(VIEWS):
            state.phase = "completed"
        self._store.save(state)

    def _choose_view(self, state: ExperimentState) -> None:
        revising = state.phase == "revising"
        name = state.revision_view if revising else state.order[len(state.proposals)]
        view = VIEWS[name]
        previous = state.proposals[name] if revising else state.previous[name]
        proposed = {path for owner, proposal in state.proposals.items() if owner != name
                    for path in proposal.values if path != DViewConversation.NEW_SEED}
        if state.new_seed:
            proposed.add(DViewConversation.NEW_SEED)
        view = replace(view, parameters=tuple(path for path in view.parameters if path not in proposed))
        context = dict(
            previous_hypothesis=previous.hypothesis,
            previous_values=previous.values,
            previous_observations="" if state.synthetic else state.observations[name],
            parameters=editable_parameters(view, state.config),
            other_parameters=other_parameters(view, state.config, proposed, new_seed=state.new_seed),
        )
        prompt = self._prompts.render(view, context, duplicate=revising)
        proposal = self._conversation.propose(view, prompt, state.experiment_id)
        if revising:
            proposal = ViewProposal(proposal.hypothesis, {**previous.values, **proposal.values})
        state.config = apply_values(state.config, proposal.values)
        seed_requested = state.new_seed
        state.new_seed = state.new_seed or proposal.values.get(DViewConversation.NEW_SEED, False)
        state.proposals[name] = proposal
        if revising or len(state.proposals) == len(state.order):
            if state.new_seed and (not revising or not seed_requested):
                state.config["seed"] += 1
                state.seed_baseline = True
            state.revision_view = None
            state.phase = "ready"
        self._store.save(state)

    def _simulation_config(self, state: ExperimentState) -> dict:
        if state.seed_baseline:
            config = deepcopy(self._completed_result(state.golden_run_id)["config"])
            config["seed"] = state.config["seed"]
            return config
        return state.config

    def _record_submission(self, state: ExperimentState) -> None:
        recorded = self._store.run_events(state.run_id)
        parent = recorded.get(Events.Configuration.PROPOSAL_ACCEPTED)
        if not state.baseline and not state.seed_baseline and parent is None:
            parent = self._events.log(Events.Configuration.PROPOSAL_ACCEPTED, Events.Configuration.CATEGORY, "INFO",
                                  json.dumps(dict(draft_id=state.experiment_id, config=state.config,
                                                  origin="synthetic" if state.synthetic else "llm"), allow_nan=False),
                                  process_id=state.run_id)
        if Events.SnakeLab.SUBMITTED not in recorded:
            description = "Submitted four-view configuration."
            if state.baseline:
                description = "Submitted baseline configuration."
            elif state.seed_baseline:
                description = "Submitted golden configuration with a new seed."
            elif state.synthetic:
                description = "Submitted synthetic four-view configuration."
            self._events.log(Events.SnakeLab.SUBMITTED, Events.SnakeLab.CATEGORY, "INFO",
                         description,
                         process_id=state.run_id, parent_event_id=parent, ax3l_version=DAx3l.VERSION)

    def _promote(self, run_id: str, reason: str) -> None:
        result = self._completed_result(run_id)
        self._configuration_log.golden_config_created(
            run_id, reason=reason, experiment_score=dict(simulations=self._snake.get_num_sims(),
                                                        score=result["high_score"], seed=result["config"]["seed"]))

    def _finish(self, state: ExperimentState) -> None:
        self._record_submission(state)
        latest = self._completed_result(state.run_id)
        if state.seed_baseline:
            winner = state.run_id
            reason = f"Established the golden baseline on seed {latest['config']['seed']}."
        elif state.baseline:
            winner = state.run_id
            reason = "Established the default configuration baseline."
        else:
            comparison = self._store.comparison(state.run_id)
            if comparison is None:
                golden = self._completed_result(state.golden_run_id)
                won = latest["high_score"] > golden["high_score"]
                winner = state.run_id if won else state.golden_run_id
                reason = f"High score: {latest['high_score']} {'>' if won else '<='} {golden['high_score']}."
                comparison = dict(golden_run_id=state.golden_run_id, latest_run_id=state.run_id,
                                  current_golden_run_id=winner, reason=reason)
                self._events.log(Events.Configuration.COMPARED, Events.Configuration.CATEGORY, "INFO",
                             json.dumps(comparison), process_id=state.run_id)
            winner, reason = comparison["current_golden_run_id"], comparison["reason"]
        current = self._events.current_golden_config()
        if current is None or current["process_id"] != winner:
            self._promote(winner, reason)
        if state.baseline and state.synthetic:
            for proposal in state.proposals.values():
                state.config = apply_values(state.config, proposal.values)
            state.baseline = False
            state.golden_run_id = winner
            state.run_id, state.preceding_match = None, None
            state.phase = "ready"
            self._store.save(state)
            return
        if state.seed_baseline:
            state.golden_run_id = winner
            state.run_id, state.preceding_match = None, None
            state.seed_baseline = False
            state.phase = "ready"
            self._store.save(state)
            return
        state.reference_run_id = state.run_id if state.baseline else state.golden_run_id
        state.golden_run_id, state.latest_run_id = winner, state.run_id
        state.observations = {}
        state.phase = "evaluating"
        self._store.save(state)
