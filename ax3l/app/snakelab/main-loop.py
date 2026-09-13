"""Run from the checkout: python3 -m ax3l.app.snakelab.main-loop --url URL."""

import argparse
import os
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import json
import random
from pathlib import Path
import time
import traceback
from uuid import uuid4

from ax3l.app.snakelab.SnakeLabLoop import run_optimization
from ax3l.app.DbMgr import DbMgr
from ax3l.app.Prompt import Prompt
from ax3l.app.ConfigurationLog import ConfigurationLog
from ax3l.app.snakelab.GenerateDefaultConfig import GenerateDefaultConfig
from ax3l.constants.DEventCategory import DEventCategory

from ax3l.app.snakelab.prompts.GenerateHaiku import GenerateHaiku
from ax3l.app.snakelab.prompts.FirstContact import FirstContact
from ax3l.app.snakelab.prompts.FirstContactSingle import FirstContactSingle
from ax3l.app.snakelab.prompts.GoldenConfig import GoldenConfig
from ax3l.constants.DSnakeLab import DSnakeLab
from ax3l.constants.DAx3l import DAx3l
from ax3l.interface.LLM import LLM
from ax3l.interface.SnakeLab import SnakeLab


def run(llm: LLM, output: Path, db: DbMgr, count: int = DSnakeLab.HAIKU_COUNT,
        *, prompts: list[Prompt] | None = None) -> None:
    process_id = str(uuid4())
    print(f"Conversation: {process_id}", flush=True)
    conversation_id = db.log(
        DEventCategory.Conversation.STARTED, DEventCategory.Conversation.CATEGORY, "INFO",
        f"Conversation started with {llm.url}."
        + (f" Output: {output.resolve()}" if DAx3l.RAW_LOGS_ENABLED else ""),
        process_id=process_id,
    )
    outcome = "Completed requested conversation."
    level = "INFO"
    try:
        turn = 0
        while count == 0 or turn < count:
            turn += 1
            snippets = prompts if prompts is not None else [GenerateHaiku(random.randint(0, 30))]
            # Serialize once: the log and request must use the same snapshots.
            messages = [json.loads(prompt.to_json()) for prompt in snippets]
            prefix = output / f"{turn:04d}"
            payload = json.dumps({
                "messages": messages,
                "stream": False,
            }, ensure_ascii=False).encode("utf-8")
            if DAx3l.RAW_LOGS_ENABLED:
                prefix.with_suffix(".request.json").write_bytes(payload)
            print(f"{datetime.now(timezone.utc).isoformat()} Request {turn}: {llm.url}", flush=True)
            for message in messages:
                prompt_id = db.log(
                    DEventCategory.Conversation.PROMPT, DEventCategory.Conversation.CATEGORY,
                    "INFO", json.dumps(message, ensure_ascii=False),
                    process_id=process_id, parent_event_id=conversation_id,
                )
            try:
                status, headers, body = llm.complete(payload)
            except Exception as error:
                db.log(
                    DEventCategory.LLM.REQUEST_FAILED, DEventCategory.LLM.CATEGORY, "ERROR", str(error),
                    process_id=process_id, parent_event_id=prompt_id,
                )
                raise
            if DAx3l.RAW_LOGS_ENABLED:
                prefix.with_suffix(".response.body").write_bytes(body)
                prefix.with_suffix(".response.headers").write_text(
                    f"HTTP status: {status}\n{headers}", encoding="utf-8"
                )
            response_text = body.decode("utf-8", errors="backslashreplace")
            if DAx3l.RAW_LOGS_ENABLED:
                print(f"HTTP status: {status}\n{headers}", flush=True)
                print(response_text, flush=True)
            if status >= 400:
                db.log(
                    DEventCategory.LLM.REQUEST_FAILED, DEventCategory.LLM.CATEGORY, "ERROR",
                    f"HTTP {status}\n{response_text}",
                    process_id=process_id, parent_event_id=prompt_id,
                )
                raise RuntimeError(f"LLM returned HTTP {status}; see the llm_request_failed event")
            reply_id = db.log(
                DEventCategory.Conversation.RESPONSE, DEventCategory.Conversation.CATEGORY, "INFO", response_text,
                process_id=process_id, parent_event_id=prompt_id,
            )
            if count == 0 or turn < count:
                wait_id = db.log(
                    DEventCategory.Process.WAIT_STARTED, DEventCategory.Process.CATEGORY, "INFO",
                    f"Sleep for seconds: ({DSnakeLab.HAIKU_SLEEP_SECONDS})",
                    process_id=process_id, parent_event_id=reply_id,
                )
                time.sleep(DSnakeLab.HAIKU_SLEEP_SECONDS)
                db.log(
                    DEventCategory.Process.WAIT_ENDED, DEventCategory.Process.CATEGORY, "INFO",
                    f"Wait completed after {DSnakeLab.HAIKU_SLEEP_SECONDS} seconds.",
                    process_id=process_id, parent_event_id=wait_id,
                )
    except KeyboardInterrupt:
        outcome = "Stopped by user."
        raise
    except Exception as error:
        outcome = f"Conversation failed: {error}"
        level = "ERROR"
        raise
    finally:
        db.log(
            DEventCategory.Conversation.ENDED, DEventCategory.Conversation.CATEGORY, level, outcome,
            process_id=process_id, parent_event_id=conversation_id,
        )


def initialize_simulation(db: DbMgr) -> None:
    """Submit the first simulation and wait for its cycle to finish."""
    snake = SnakeLab()
    if snake.get_num_sims() != 0:
        return
    run_id = snake.submit_simulation(GenerateDefaultConfig().run())
    submitted_id = db.log(
        DEventCategory.SnakeLab.SUBMITTED, DEventCategory.SnakeLab.CATEGORY, "INFO", "Submitted config.",
        process_id=run_id,
    )
    ConfigurationLog(db).golden_config_created(
        run_id, reason="Seeded database with default config.", parent_event_id=submitted_id,
    )
    started = False
    while True:
        time.sleep(DSnakeLab.STATUS_POLL_SECONDS)
        state = snake.get_simulation_status(run_id)
        if state == "running" and not started:
            db.log(
                DEventCategory.SnakeLab.STARTED, DEventCategory.SnakeLab.CATEGORY, "INFO", "Simulation started running.",
                process_id=run_id, parent_event_id=submitted_id,
            )
            started = True
        if state in ("completed", "failed", "cancelled"):
            db.log(
                DEventCategory.SnakeLab.TERMINAL_EVENTS[state], DEventCategory.SnakeLab.CATEGORY, "ERROR" if state == "failed" else "INFO",
                f"Simulation {state}." if started else
                f"Simulation {state} before running status was observed.",
                process_id=run_id, parent_event_id=submitted_id,
            )
            return


def run_first_iteration(llm: LLM, output: Path, db: DbMgr) -> None:
    snake = SnakeLab()
    while snake.is_simulation_running():
        time.sleep(DSnakeLab.STATUS_POLL_SECONDS)
    first_contact = FirstContact()
    golden = GoldenConfig(db)
    parameter = FirstContactSingle()
    run(llm, output, db, count=1, prompts=[first_contact, golden, parameter])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Snake Lab single-parameter optimization loop.")
    parser.add_argument("--url", required=True, help="LLM server base URL, e.g. http://host:27770")
    parser.add_argument("--output", type=Path, default=Path("tmp/haiku"))
    parser.add_argument("--zmq-endpoint", default=os.environ.get("AX3L_ZMQ_ENDPOINT", DAx3l.ZMQ_ENDPOINT))
    args = parser.parse_args(argv)
    output = args.output
    with ExitStack() as captures:
        if DAx3l.RAW_LOGS_ENABLED:
            output = output / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
            output.mkdir(parents=True)
            print(f"Capturing output in {output.resolve()}", flush=True)
            log = captures.enter_context((output / "run.log").open("w", encoding="utf-8", buffering=1))
            captures.enter_context(redirect_stdout(log))
            captures.enter_context(redirect_stderr(log))
        try:
            db = DbMgr()
            try:
                initialize_simulation(db)
                run_optimization(LLM(args.url), output, db, args.zmq_endpoint)
            finally:
                db.close()
        except KeyboardInterrupt:
            print("Stopped by user.")
            return 130
        except Exception:
            traceback.print_exc()
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
