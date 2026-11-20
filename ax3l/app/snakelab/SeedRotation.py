"""Establish a fresh golden baseline before testing changes on a new seed."""

from copy import deepcopy
import json

from ax3l.app.ConfigurationLog import ConfigurationLog
from ax3l.app.EventLogDb import EventLogDb
from ax3l.app.snakelab.ExperimentDb import ExperimentDb
from ax3l.constants.DAx3l import DAx3l
from ax3l.constants.DEventCategory import DEventCategory as Events
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


async def resume_seed_rotation(snake, db, wait_for_run) -> str | None:
    """Finish an interrupted rotation from the former automatic policy."""
    pending = EventLogDb(db).pending_seed_rotation()
    if pending is None:
        return None
    return await _complete_seed_rotation(snake, db, pending, wait_for_run)


async def rotate_draft_seed(snake, db, experiments: ExperimentDb,
                            draft: ConfigurationDraft, wait_for_run) -> None:
    baseline = deepcopy(snake.get_run_result(draft.golden_run_id)["config"])
    if baseline["seed"] == draft.config["seed"]:
        return
    SimulationConfiguration.validate(draft.config)
    baseline["seed"] = draft.config["seed"]
    if draft.phase == "ready":
        draft.phase = "rotating_seed"
        experiments.save_draft(draft)
    rotation = EventLogDb(db).seed_rotation(draft.draft_id)
    if rotation is None:
        content = json.dumps({"draft_id": draft.draft_id, "config": baseline}, allow_nan=False)
        event_id = db.log(Events.Configuration.SEED_ROTATION_STARTED, Events.Configuration.CATEGORY,
                          "INFO", content, process_id=draft.draft_id, ax3l_version=DAx3l.VERSION)
        rotation = dict(event_id=event_id, content=content, ax3l_version=DAx3l.VERSION,
                        run_id=snake.submit_simulation(baseline))
        _record_submission(db, rotation)
        run_id = await _complete_seed_rotation(snake, db, rotation, wait_for_run)
    elif rotation["completed_event_id"] is not None:
        run_id = rotation["run_id"]
    else:
        run_id = await _complete_seed_rotation(snake, db, rotation, wait_for_run)
    draft.golden_run_id = run_id
    draft.references["golden"] = run_id
    if draft.config == baseline:
        draft.run_id = run_id
        draft.phase = "submitted"
    else:
        draft.phase = "ready"
    experiments.save_draft(draft)


def _record_submission(db, rotation: dict) -> None:
    rotation["submitted_event_id"] = db.log(
        Events.Configuration.GOLDEN_SEED_INCREMENTED, Events.Configuration.CATEGORY, "INFO",
        "Submitted golden configuration with the requested seed for a fresh baseline.",
        process_id=rotation["run_id"], parent_event_id=rotation["event_id"])
    db.log(Events.SnakeLab.SUBMITTED, Events.SnakeLab.CATEGORY, "INFO",
           "Submitted config for a fresh baseline.", process_id=rotation["run_id"],
           parent_event_id=rotation["submitted_event_id"], ax3l_version=rotation.get("ax3l_version"))


async def _complete_seed_rotation(snake, db, pending: dict, wait_for_run) -> str:
    config = json.loads(pending["content"])["config"]
    run_id = pending["run_id"]
    if run_id is None:
        # Reconcile an interrupted/ambiguous submission by full config, never by retrying it.
        run_id = snake.find_config_run(config)
        if run_id is None:
            raise RuntimeError("Seed rotation submission is unresolved; no matching simulation was found")
        pending["run_id"] = run_id
        _record_submission(db, pending)
    await wait_for_run(snake, db, run_id)
    result = snake.get_run_result(run_id)
    if result is None or result["status"] != "completed" or result["high_score"] is None:
        raise ValueError("Seed baseline requires a completed simulation with a recorded high score")
    ConfigurationLog(db).golden_config_created(
        run_id, reason=f"Fresh baseline after seed rotation. Score to beat: {result['high_score']}.",
        parent_event_id=pending["submitted_event_id"],
        experiment_score={"simulations": snake.get_num_sims(), "score": result["high_score"],
                          "seed": config["seed"]})
    return run_id
