"""Choose every setting in a durable draft, run once, and analyze the result."""

import asyncio
from copy import deepcopy
import json
from uuid import uuid4

from ax3l.app.ConfigurationLog import ConfigurationLog
from ax3l.app.EventLogDb import EventLogDb
from ax3l.app.snakelab.ToolConversation import converse
from ax3l.app.snakelab.SeedRotation import rotate_if_needed
from ax3l.app.snakelab.AnalyzeRun import analyze_run
from ax3l.app.snakelab.ExperimentDb import ExperimentDb
from ax3l.app.snakelab.prompts.ConfigurationChoice import ConfigurationChoice
from ax3l.app.snakelab.prompts.ProjectContext import ProjectContext
from ax3l.constants.DAx3l import DAx3l
from ax3l.constants.DEventCategory import DEventCategory as Events
from ax3l.constants.DSnakeLab import DSnakeLab
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
from ax3l.interface.SnakeLab import SnakeLab, SimulationUnavailable
from ax3l.interface.SnakeLabTools import SnakeLabTools
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


class SimulationUnsuccessful(RuntimeError):
    """A simulation ended without completed results to compare."""


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
    snake = SnakeLab()
    experiments = ExperimentDb(db)
    while snake.is_simulation_running():
        await asyncio.sleep(DSnakeLab.STATUS_POLL_SECONDS)
    await rotate_if_needed(snake, db, wait_for_run, resume_only=True)
    while True:
        draft = experiments.draft()
        if draft is None or draft.phase in ("completed", "failed"):
            await rotate_if_needed(snake, db, wait_for_run)
            golden_id = EventLogDb(db).current_golden_config()["process_id"]
            baseline = snake.get_run_result(golden_id)
            if baseline is None or baseline["status"] != "completed" or baseline["high_score"] is None:
                raise ValueError("The golden simulation must have completed with a high score")
            references = {"latest": snake.get_latest_completed_run_id(), "golden": golden_id,
                          "all_time_best": snake.get_all_time_best_run_id()}
            draft = ConfigurationDraft(str(uuid4()), golden_id, references,
                                       deepcopy(baseline["config"]), phase="preparing")
            experiments.save_draft(draft)
        if draft.phase in ("preparing", "choosing"):
            if draft.phase == "choosing":
                draft.phase = "preparing"
                experiments.save_draft(draft)
            target = snake.get_run_result(draft.golden_run_id)["high_score"]
            analyses = {}
            for run_id in dict.fromkeys(draft.references.values()):
                analyses[run_id] = await analyze_run(snake, llm, output, db, endpoint, run_id, target)
            draft.phase = "choosing"
            experiments.save_draft(draft)
            while draft.phase == "choosing":
                parameter = draft.next_parameter
                prompts = [ProjectContext(), ConfigurationChoice(draft, analyses)]
                async with SnakeLabTools(endpoint, parameter, draft_id=draft.draft_id) as tools:
                    await converse(llm, output, db, tools, prompts,
                                   parameter=parameter, process_id=draft.draft_id)
                draft = experiments.draft(draft.draft_id)
        submit_draft(snake, db, experiments, draft)
        try:
            await wait_for_run(snake, db, draft.run_id)
        except SimulationUnsuccessful:
            draft.phase = "failed"
            experiments.save_draft(draft)
            raise
        golden_id = complete_comparison(snake, db, experiments, draft)
        target = snake.get_run_result(golden_id)["high_score"]
        await analyze_run(snake, llm, output, db, endpoint, draft.run_id, target)
        draft.phase = "completed"
        experiments.save_draft(draft)


def run_optimization(llm, output, db, endpoint):
    asyncio.run(optimize(llm, output, db, endpoint))
