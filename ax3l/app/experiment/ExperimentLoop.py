"""Evaluate results in four conversations before assembling four new proposals."""

from collections.abc import Callable
from copy import deepcopy
import json
from random import shuffle
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
from ax3l.entities.ExperimentState import ExperimentState
from ax3l.entities.ExperimentView import VIEWS
from ax3l.entities.ViewProposal import ViewProposal
from ax3l.interface.LLM import LLM
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
            elif state.phase == "choosing":
                self._choose_view(state)
            elif state.phase == "ready":
                SimulationConfiguration.validate(state.config)
                state.preceding_match = self._snake.find_config_run(state.config)
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
            elif state.phase == "evaluating":
                self._evaluate_view(state)
                if state.phase == "completed" and not state.baseline and state.proposals:
                    completed += 1
            else:
                raise ValueError(f"Unknown experiment phase: {state.phase}")

    def _initialize(self) -> ExperimentState:
        golden = self._events.current_golden_config()
        run_id = golden["process_id"] if golden else self._snake.get_all_time_best_run_id()
        config = self._completed_result(run_id)["config"] if run_id else SimulationConfiguration.defaults()
        previous = {
            name: ViewProposal(view.initial_hypothesis, view_values(view, config))
            for name, view in VIEWS.items()
        }
        state = ExperimentState(str(uuid4()), "evaluating" if run_id else "ready", deepcopy(config),
                                baseline=run_id is None, golden_run_id=run_id, latest_run_id=run_id,
                                reference_run_id=run_id, previous=previous)
        if run_id and golden is None:
            self._promote(run_id, "Adopted the best completed simulation as the initial baseline.")
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
            previous_seeded=not bool(previous.proposals),
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
        content = self._prompts.render_evaluation(view, context)
        state.observations[name] = self._conversation.evaluate(view, content, state.experiment_id)
        if len(state.observations) == len(VIEWS):
            state.phase = "completed"
        self._store.save(state)

    def _choose_view(self, state: ExperimentState) -> None:
        name = state.order[len(state.proposals)]
        view = VIEWS[name]
        previous = state.previous[name]
        proposed = {path for proposal in state.proposals.values() for path in proposal.values}
        context = dict(
            previous_hypothesis=previous.hypothesis,
            previous_values=previous.values,
            previous_observations=state.observations[name],
            parameters=editable_parameters(view, state.config),
            other_parameters=other_parameters(view, state.config, proposed),
        )
        prompt = self._prompts.render(view, context)
        proposal = self._conversation.propose(view, prompt, state.config, state.experiment_id)
        state.config = apply_values(state.config, proposal.values)
        state.proposals[name] = proposal
        if len(state.proposals) == len(state.order):
            state.phase = "ready"
        self._store.save(state)

    def _record_submission(self, state: ExperimentState) -> None:
        recorded = self._store.run_events(state.run_id)
        parent = recorded.get(Events.Configuration.PROPOSAL_ACCEPTED)
        if not state.baseline and parent is None:
            parent = self._events.log(Events.Configuration.PROPOSAL_ACCEPTED, Events.Configuration.CATEGORY, "INFO",
                                  json.dumps(dict(draft_id=state.experiment_id, config=state.config), allow_nan=False),
                                  process_id=state.run_id)
        if Events.SnakeLab.SUBMITTED not in recorded:
            self._events.log(Events.SnakeLab.SUBMITTED, Events.SnakeLab.CATEGORY, "INFO",
                         "Submitted baseline configuration." if state.baseline else "Submitted four-view configuration.",
                         process_id=state.run_id, parent_event_id=parent, ax3l_version=DAx3l.VERSION)

    def _promote(self, run_id: str, reason: str) -> None:
        result = self._completed_result(run_id)
        self._configuration_log.golden_config_created(
            run_id, reason=reason, experiment_score=dict(simulations=self._snake.get_num_sims(),
                                                        score=result["high_score"], seed=result["config"]["seed"]))

    def _finish(self, state: ExperimentState) -> None:
        self._record_submission(state)
        latest = self._completed_result(state.run_id)
        if state.baseline:
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
        state.reference_run_id = state.run_id if state.baseline else state.golden_run_id
        state.golden_run_id, state.latest_run_id = winner, state.run_id
        state.observations = {}
        state.phase = "evaluating"
        self._store.save(state)
