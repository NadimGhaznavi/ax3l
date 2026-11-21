"""Let Qwen refine a durable draft and choose when to run a unique configuration."""

import asyncio
from copy import deepcopy
import json
from time import monotonic, time
from uuid import uuid4

from ax3l.activity.RunAnalysis import render_analysis
from ax3l.app.ConfigurationLog import ConfigurationLog
from ax3l.app.EventLogDb import EventLogDb
from ax3l.app.snakelab.ToolConversation import converse, DecisionTimeExpired
from ax3l.app.snakelab.SeedRotation import resume_seed_rotation, rotate_draft_seed
from ax3l.app.snakelab.AnalyzeRun import record_run_metrics
from ax3l.app.snakelab.ExperimentDb import ExperimentDb
from ax3l.app.snakelab.prompts.ConfigurationChoice import ConfigurationChoice
from ax3l.app.snakelab.prompts.ConfigurationNextStep import ConfigurationNextStep
from ax3l.constants.DAx3l import DAx3l
from ax3l.constants.DChoice import (
    CHOICE_CHARTS, IMAGE_PROMPT_EXTRA_SECONDS, PARAMETER_SELECTION_SECONDS, REVISION_PARAMETER,
)
from ax3l.constants.DEventCategory import DEventCategory as Events
from ax3l.constants.DSimulationAnalysis import DSimulationAnalysis
from ax3l.constants.DSnakeLab import DSnakeLab
from ax3l.entities.ConfigurationDraft import ConfigurationDraft, PARAMETER_ORDER
from ax3l.entities.EpsilonNiceChoice import EpsilonNiceChoice
from ax3l.interface.Configuration import Configuration
from ax3l.interface.SnakeLab import SnakeLab, SimulationUnavailable
from ax3l.interface.SnakeLabTools import SnakeLabTools
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


class SimulationUnsuccessful(RuntimeError):
    """A simulation ended without completed results to compare."""


async def prepare_chart(db, draft_id, parameter, section, run, episodes, target, *,
                        golden_episodes: list[dict] | None = None):
    category = Events.Configuration
    title = DSimulationAnalysis.CHART_LABELS[section]
    fields = dict(process_id=draft_id, parameter=parameter)
    db.log(category.CHART_STARTED, category.CATEGORY, "INFO", title, **fields)
    try:
        png = await asyncio.to_thread(render_analysis, run.config, episodes, run.metrics, target, section,
                                      golden_episodes=golden_episodes)
    except BaseException as error:
        state = "Stopped" if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt)) else "Failed"
        db.log(category.CHART_FINISHED, category.CATEGORY, "ERROR", state, **fields)
        raise
    db.log(category.CHART_FINISHED, category.CATEGORY, "INFO", "Complete", **fields)
    return png


async def wait_for_run(snake, db, run_id):
    started = False
    while True:
        try:
            state = snake.get_simulation_status(run_id)
        except SimulationUnavailable as error:
            db.log(Events.SnakeLab.FAILED, Events.SnakeLab.CATEGORY, "ERROR",
                   str(error), process_id=run_id)
            raise
        if state == "running" and not started:
            db.log(Events.SnakeLab.STARTED, Events.SnakeLab.CATEGORY, "INFO",
                   "Simulation started running.", process_id=run_id)
            started = True
        if state in Events.SnakeLab.TERMINAL_EVENTS:
            db.log(Events.SnakeLab.TERMINAL_EVENTS[state], Events.SnakeLab.CATEGORY,
                   "INFO" if state == "completed" else "ERROR", f"Simulation {state}.", process_id=run_id)
            if state != "completed":
                raise SimulationUnsuccessful(f"Simulation {run_id} {state}; cannot compare completed results")
            return
        await asyncio.sleep(DSnakeLab.STATUS_POLL_SECONDS)


def compare(snake, db, golden_id, latest_id):
    golden = snake.get_run_result(golden_id)
    latest = snake.get_run_result(latest_id)
    for result in (golden, latest):
        if result is None or result["status"] != "completed" or result["high_score"] is None:
            raise ValueError("Comparison requires two completed simulations with recorded high scores")
    won = latest["high_score"] > golden["high_score"]
    current_id = latest_id if won else golden_id

    def changes(before, after, path=""):
        for key in before:
            name = f"{path}.{key}" if path else key
            if isinstance(before[key], dict):
                yield from changes(before[key], after[key], name)
            elif before[key] != after[key]:
                yield f"{name}: {before[key]} -> {after[key]}"

    reason = (f"High score: {latest['high_score']} {'>' if won else '<='} {golden['high_score']}; "
              + "; ".join(changes(golden["config"], latest["config"])) + ".")
    comparison_id = db.log(Events.Configuration.COMPARED, Events.Configuration.CATEGORY, "INFO",
                          json.dumps({"golden_run_id": golden_id, "latest_run_id": latest_id,
                                      "current_golden_run_id": current_id, "reason": reason}),
                          process_id=latest_id)
    if won:
        ConfigurationLog(db).golden_config_created(latest_id, reason=reason, parent_event_id=comparison_id,
            experiment_score={"simulations": snake.get_num_sims(), "score": latest["high_score"],
                              "seed": latest["config"].get("seed")})
    else:
        db.log(Events.Configuration.GOLDEN_RETAINED, Events.Configuration.CATEGORY, "INFO", reason,
               process_id=golden_id, parent_event_id=comparison_id)
    return current_id


def submit_draft(snake, db, experiments: ExperimentDb, draft: ConfigurationDraft) -> None:
    """Persist submission intent; reconcile an interrupted send without retrying it."""
    if draft.phase == "ready":
        SimulationConfiguration.validate(draft.config)
        draft.phase = "submitting"
        experiments.save_draft(draft)
        draft.run_id = snake.submit_simulation(draft.config)
        draft.phase = "submitted"
        experiments.save_draft(draft)
    elif draft.phase == "submitting":
        draft.run_id = snake.find_config_run(draft.config)
        if draft.run_id is None:
            raise RuntimeError("Configuration submission is unresolved; no matching run was found. "
                               "The submission will not be retried automatically.")
        draft.phase = "submitted"
        experiments.save_draft(draft)
    recorded = experiments.submission_events(draft.run_id)
    category = Events.Configuration
    accepted_id = recorded.get(category.PROPOSAL_ACCEPTED)
    if accepted_id is None:
        accepted_id = db.log(category.PROPOSAL_ACCEPTED, category.CATEGORY, "INFO",
                             json.dumps({"draft_id": draft.draft_id, "config": draft.config}, allow_nan=False),
                             process_id=draft.run_id)
    if Events.SnakeLab.SUBMITTED not in recorded:
        db.log(Events.SnakeLab.SUBMITTED, Events.SnakeLab.CATEGORY, "INFO", "Submitted complete configuration.",
               process_id=draft.run_id, parent_event_id=accepted_id, ax3l_version=DAx3l.VERSION)


def complete_comparison(snake, db, experiments: ExperimentDb, draft: ConfigurationDraft) -> str:
    saved = experiments.comparison(draft.run_id)
    if saved is None:
        return compare(snake, db, draft.golden_run_id, draft.run_id)
    selected_id = saved["current_golden_run_id"]
    if EventLogDb(db).current_golden_config()["process_id"] != selected_id:
        selected = snake.get_run_result(selected_id)
        ConfigurationLog(db).golden_config_created(
            selected_id, reason=saved["reason"], parent_event_id=saved["event_id"],
            experiment_score={"simulations": snake.get_num_sims(), "score": selected["high_score"],
                              "seed": selected["config"]["seed"]})
    return selected_id


async def optimize(llm, output, db, endpoint):
    decision_grace_seconds = Configuration().decision_grace_seconds
    snake = SnakeLab()
    experiments = ExperimentDb(db)
    while snake.is_simulation_running():
        await asyncio.sleep(DSnakeLab.STATUS_POLL_SECONDS)
    await resume_seed_rotation(snake, db, wait_for_run)
    while True:
        draft = experiments.draft()
        if draft is None or draft.phase in ("completed", "failed"):
            golden_id = EventLogDb(db).current_golden_config()["process_id"]
            baseline = snake.get_run_result(golden_id)
            if baseline is None or baseline["status"] != "completed" or baseline["high_score"] is None:
                raise ValueError("The golden simulation must have completed with a high score")
            references = {"latest": snake.get_latest_completed_run_id(), "golden": golden_id,
                          "all_time_best": snake.get_all_time_best_run_id()}
            draft = ConfigurationDraft(str(uuid4()), golden_id, references,
                                       deepcopy(baseline["config"]), phase="preparing")
            experiments.save_draft(draft)
        if draft.phase in ("preparing", "choosing", "selecting_parameter", "reviewing"):
            references = {run_id: record_run_metrics(snake, experiments, run_id)
                          for run_id in dict.fromkeys(draft.references.values())}
            golden = references[draft.golden_run_id]
            latest = references[draft.references["latest"]]
            chart_episodes = {}
            if draft.phase == "preparing":
                draft.phase = "selecting_parameter"
            if draft.phase == "choosing" and not snake.available_parameters(draft.config, [draft.parameter]):
                draft.parameter = None
                draft.phase = "reviewing" if draft.selections else "selecting_parameter"
            decision_deadline = monotonic() + PARAMETER_SELECTION_SECONDS
            draft.decision_expires_at = time() + PARAMETER_SELECTION_SECONDS
            experiments.save_draft(draft)
            while draft.phase in ("choosing", "selecting_parameter", "reviewing"):
                parameter = draft.next_parameter if draft.phase == "choosing" else REVISION_PARAMETER
                chart_scope = ("latest" if latest.run_id != golden.run_id
                               and latest.config["seed"] == draft.config["seed"] else "golden")
                chart_run = latest if chart_scope == "latest" else golden
                section = CHOICE_CHARTS.get(parameter)
                png = None
                if section and (section != "loss" or chart_run.metrics["episodes_with_loss"]):
                    if chart_run.run_id not in chart_episodes:
                        chart_episodes[chart_run.run_id] = snake.get_analysis_episodes(chart_run.run_id)
                    golden_episodes = None
                    if (section == "loss" and chart_run.run_id != golden.run_id
                            and golden.metrics["episodes_with_loss"]):
                        if golden.run_id not in chart_episodes:
                            chart_episodes[golden.run_id] = snake.get_analysis_episodes(golden.run_id)
                        golden_episodes = chart_episodes[golden.run_id]
                    png = await prepare_chart(db, draft.draft_id, parameter, section, chart_run,
                                              chart_episodes[chart_run.run_id], golden.metrics["high_score"],
                                              golden_episodes=golden_episodes)
                if parameter == REVISION_PARAMETER:
                    parameters = snake.available_parameters(
                        draft.config, [name for name in PARAMETER_ORDER if name not in draft.selections])
                    prompt = ConfigurationNextStep(draft, parameters)
                else:
                    choice = EpsilonNiceChoice if parameter == "epsilon_nice_pair" else ConfigurationChoice
                    prompt = choice(draft, latest, golden, chart_scope, png)
                if png is not None:
                    decision_deadline += IMAGE_PROMPT_EXTRA_SECONDS
                    draft.decision_expires_at += IMAGE_PROMPT_EXTRA_SECONDS
                    experiments.save_draft(draft)
                selected_count = len(draft.selections)
                async with SnakeLabTools(endpoint, parameter, draft_id=draft.draft_id,
                                         allow_run=draft.phase == "reviewing") as tools:
                    try:
                        await converse(llm, output, db, tools, [prompt],
                                       parameter=parameter, process_id=draft.draft_id,
                                       conversation_deadline=decision_deadline + decision_grace_seconds,
                                       reset_on_expiry=not draft.selections)
                    except DecisionTimeExpired:
                        draft = experiments.draft(draft.draft_id)
                        if draft.selections:
                            if not snake.is_config_unique(draft.config):
                                raise ValueError("The saved configuration is no longer unique; cannot submit it automatically.")
                            draft.phase = "ready"
                        else:
                            draft.phase = "selecting_parameter"
                            decision_deadline = monotonic() + PARAMETER_SELECTION_SECONDS
                            draft.decision_expires_at = time() + PARAMETER_SELECTION_SECONDS
                        draft.parameter = None
                        experiments.save_draft(draft)
                draft = experiments.draft(draft.draft_id)
                if draft.phase == "reviewing" and len(draft.selections) > selected_count:
                    decision_deadline = monotonic() + PARAMETER_SELECTION_SECONDS
                    draft.decision_expires_at = time() + PARAMETER_SELECTION_SECONDS
                    experiments.save_draft(draft)
        try:
            if draft.phase in ("ready", "rotating_seed"):
                await rotate_draft_seed(snake, db, experiments, draft, wait_for_run)
            if draft.run_id != draft.golden_run_id:
                submit_draft(snake, db, experiments, draft)
                await wait_for_run(snake, db, draft.run_id)
                complete_comparison(snake, db, experiments, draft)
        except SimulationUnsuccessful:
            draft.phase = "failed"
            experiments.save_draft(draft)
            raise
        record_run_metrics(snake, experiments, draft.run_id)
        draft.phase = "completed"
        experiments.save_draft(draft)


def run_optimization(llm, output, db, endpoint):
    asyncio.run(optimize(llm, output, db, endpoint))
