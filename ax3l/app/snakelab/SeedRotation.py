"""Finish seed rotations recorded before LLM-requested seed changes replaced them."""

import json

from ax3l.app.ConfigurationLog import ConfigurationLog
from ax3l.app.EventLogDb import EventLogDb
from ax3l.constants.DEventCategory import DEventCategory as Events


async def resume_seed_rotation(snake, db, wait_for_run) -> str | None:
    events = EventLogDb(db)
    pending = events.pending_seed_rotation()
    if pending is None:
        return None
    config = json.loads(pending["content"])["config"]
    run_id = pending["run_id"]
    if run_id is None:
        # Reconcile an interrupted/ambiguous submission by full config, never by retrying it.
        run_id = snake.find_config_run(config)
        if run_id is None:
            raise RuntimeError("Seed rotation submission is unresolved; no matching simulation was found")
        pending["submitted_event_id"] = db.log(
            Events.Configuration.GOLDEN_SEED_INCREMENTED, Events.Configuration.CATEGORY, "INFO",
            "Submitted golden configuration with the next seed after stagnant configuration proposals.",
            process_id=run_id, parent_event_id=pending["event_id"])
        db.log(Events.SnakeLab.SUBMITTED, Events.SnakeLab.CATEGORY, "INFO",
               "Submitted config for a fresh baseline.", process_id=run_id,
               parent_event_id=pending["submitted_event_id"], ax3l_version=pending.get("ax3l_version"))
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
