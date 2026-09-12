"""Alternate MCP submissions, completed simulations, and fresh comparisons."""

import asyncio
import json

from ax3l.app.ConfigurationLog import ConfigurationLog
from ax3l.app.EventLogDb import EventLogDb
from ax3l.app.snakelab.ToolConversation import converse
from ax3l.app.snakelab.SeedRotation import rotate_if_needed
from ax3l.app.snakelab.prompts.Comparison import Comparison
from ax3l.app.snakelab.prompts.ComparisonSingle import ComparisonSingle
from ax3l.app.snakelab.prompts.ComparisonPlot import ComparisonPlot
from ax3l.app.snakelab.prompts.FirstContact import FirstContact
from ax3l.app.snakelab.prompts.FirstContactSingle import FirstContactSingle
from ax3l.app.snakelab.prompts.GoldenConfig import GoldenConfig
from ax3l.app.snakelab.prompts.LossPlot import LossPlot
from ax3l.constants.DEventCategory import DEventCategory as Events
from ax3l.constants.DSnakeLab import DSnakeLab
from ax3l.interface.SnakeLab import SnakeLab
from ax3l.interface.SnakeLabTools import SnakeLabTools


async def wait_for_run(snake, db, run_id):
    started = False
    while True:
        state = snake.get_simulation_status(run_id)
        if state == "running" and not started:
            db.log(Events.SnakeLab.STARTED, Events.SnakeLab.CATEGORY, "INFO",
                   "Simulation started running.", process_id=run_id)
            started = True
        if state in Events.SnakeLab.TERMINAL_EVENTS:
            db.log(Events.SnakeLab.TERMINAL_EVENTS[state], Events.SnakeLab.CATEGORY,
                   "INFO" if state == "completed" else "ERROR", f"Simulation {state}.", process_id=run_id)
            if state != "completed":
                raise RuntimeError(f"Simulation {run_id} {state}; cannot compare completed results")
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
    reason = (f"High score: {latest['high_score']} {'>' if won else '<='} {golden['high_score']}; "
              f"learning_rate: {golden['config']['training']['learning_rate']} -> "
              f"{latest['config']['training']['learning_rate']}.")
    comparison_id = db.log(Events.Configuration.COMPARED, Events.Configuration.CATEGORY, "INFO",
                          json.dumps({"golden_run_id": golden_id, "latest_run_id": latest_id,
                                      "current_golden_run_id": current_id, "reason": reason}),
                          process_id=latest_id)
    if won:
        ConfigurationLog(db).golden_config_created(latest_id, reason=reason, parent_event_id=comparison_id)
    else:
        db.log(Events.Configuration.GOLDEN_RETAINED, Events.Configuration.CATEGORY, "INFO", reason,
               process_id=golden_id, parent_event_id=comparison_id)
    return current_id


async def optimize(llm, output, db, endpoint):
    snake = SnakeLab()
    while snake.is_simulation_running():
        await asyncio.sleep(DSnakeLab.STATUS_POLL_SECONDS)
    await rotate_if_needed(snake, db, wait_for_run, resume_only=True)
    golden = GoldenConfig(db)
    golden_id = golden.run_id
    baseline = snake.get_run_result(golden_id)
    if baseline is None or baseline["status"] != "completed" or baseline["high_score"] is None:
        raise ValueError("The initial golden simulation must have completed with a high score")
    proposal = EventLogDb(db).latest_snakelab_proposal()
    if proposal:
        latest_id = proposal["process_id"]
        if proposal["comparison"]:
            snapshot = json.loads(proposal["comparison"])
            previous_golden_id = snapshot["golden_run_id"]
            selected_id = snapshot["current_golden_run_id"]
            # Finish a promotion interrupted between the comparison and creation events.
            if selected_id != golden_id:
                ConfigurationLog(db).golden_config_created(
                    selected_id, reason=snapshot["reason"], parent_event_id=proposal["comparison_id"])
            golden_id = selected_id
        else:
            await wait_for_run(snake, db, latest_id)
            previous_golden_id = golden_id
            golden_id = compare(snake, db, golden_id, latest_id)
        prompts = [Comparison(previous_golden_id, latest_id, golden_id), ComparisonSingle(),
                   ComparisonPlot(previous_golden_id, latest_id)]
    elif EventLogDb(db).latest_seed_baseline() is not None:
        prompts = [Comparison(golden_id, golden_id, golden_id), ComparisonSingle(), LossPlot(golden_id)]
    else:
        prompts = [FirstContact(), golden, LossPlot(golden_id), FirstContactSingle("learning_rate")]
    async with SnakeLabTools(endpoint) as tools:
        while True:
            rotated_id = await rotate_if_needed(snake, db, wait_for_run)
            if rotated_id is not None:
                golden_id = rotated_id
                prompts = [Comparison(golden_id, golden_id, golden_id), ComparisonSingle(), LossPlot(golden_id)]
            latest_id = await converse(llm, output, db, tools, prompts)
            await wait_for_run(snake, db, latest_id)
            while snake.is_simulation_running():
                await asyncio.sleep(DSnakeLab.STATUS_POLL_SECONDS)
            previous_golden_id = golden_id
            golden_id = compare(snake, db, previous_golden_id, latest_id)
            prompts = [Comparison(previous_golden_id, latest_id, golden_id), ComparisonSingle(),
                       ComparisonPlot(previous_golden_id, latest_id)]


def run_optimization(llm, output, db, endpoint):
    asyncio.run(optimize(llm, output, db, endpoint))
