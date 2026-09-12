"""Run from the checkout: python3 -m ax3l.app.snakelab.main-loop --url URL."""

import argparse
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import json
import random
from pathlib import Path
import time
import traceback
from uuid import uuid4

from ax3l.app.DbMgr import DbMgr
from ax3l.app.snakelab.GenerateDefaultConfig import GenerateDefaultConfig
from ax3l.constants.DConversation import DConversation

from ax3l.app.snakelab.prompts.GenerateHaiku import GenerateHaiku
from ax3l.constants.DSnakeLab import DSnakeLab
from ax3l.constants.DAx3l import DAx3l
from ax3l.interface.LLM import LLM
from ax3l.interface.SnakeLab import SnakeLab


def run(llm: LLM, output: Path, db: DbMgr, count: int = DSnakeLab.HAIKU_COUNT) -> None:
    process_id = str(uuid4())
    print(f"Conversation: {process_id}", flush=True)
    conversation_id = db.log(
        DConversation.STARTED, DConversation.CATEGORY, "INFO",
        f"Haiku conversation started with {llm.url}."
        + (f" Output: {output.resolve()}" if DAx3l.RAW_LOGS_ENABLED else ""),
        process_id=process_id,
    )
    outcome = "Completed requested haiku turns."
    level = "INFO"
    try:
        turn = 0
        while count == 0 or turn < count:
            turn += 1
            prompt = GenerateHaiku(random.randint(0, 30))
            prefix = output / f"{turn:04d}"
            payload = json.dumps({
                "messages": [json.loads(prompt.to_json())],
                "stream": False,
            }, ensure_ascii=False).encode("utf-8")
            if DAx3l.RAW_LOGS_ENABLED:
                prefix.with_suffix(".request.json").write_bytes(payload)
            print(f"{datetime.now(timezone.utc).isoformat()} Request {turn}: {llm.url}", flush=True)
            prompt_id = db.log(
                DConversation.PROMPT, DConversation.CATEGORY, "INFO", prompt.to_md(),
                process_id=process_id, parent_event_id=conversation_id,
            )
            try:
                status, headers, body = llm.complete(payload)
            except Exception as error:
                db.log(
                    "llm_request_failed", "LLM", "ERROR", str(error),
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
                    "llm_request_failed", "LLM", "ERROR",
                    f"HTTP {status}\n{response_text}",
                    process_id=process_id, parent_event_id=prompt_id,
                )
                raise RuntimeError(f"LLM returned HTTP {status}; see the llm_request_failed event")
            reply_id = db.log(
                DConversation.RESPONSE, DConversation.CATEGORY, "INFO", response_text,
                process_id=process_id, parent_event_id=prompt_id,
            )
            if count == 0 or turn < count:
                wait_id = db.log(
                    "wait_started", "Process", "INFO",
                    f"Sleep for seconds: ({DSnakeLab.HAIKU_SLEEP_SECONDS})",
                    process_id=process_id, parent_event_id=reply_id,
                )
                time.sleep(DSnakeLab.HAIKU_SLEEP_SECONDS)
                db.log(
                    "wait_ended", "Process", "INFO",
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
            DConversation.ENDED, DConversation.CATEGORY, level, outcome,
            process_id=process_id, parent_event_id=conversation_id,
        )


def initialize_simulation(db: DbMgr) -> None:
    """Submit the first simulation and wait for its cycle to finish."""
    snake = SnakeLab()
    if snake.get_num_sims() != 0:
        return
    run_id = snake.submit_simulation(GenerateDefaultConfig().run())
    submitted_id = db.log(
        "simulation_submitted", "SnakeLab", "INFO", "Submitted config.",
        process_id=run_id,
    )
    started = False
    while True:
        time.sleep(DSnakeLab.STATUS_POLL_SECONDS)
        state = snake.get_simulation_status(run_id)
        if state == "running" and not started:
            db.log(
                "simulation_started", "SnakeLab", "INFO", "Simulation started running.",
                process_id=run_id, parent_event_id=submitted_id,
            )
            started = True
        if state in ("completed", "failed", "cancelled"):
            db.log(
                f"simulation_{state}", "SnakeLab", "ERROR" if state == "failed" else "INFO",
                f"Simulation {state}." if started else
                f"Simulation {state} before running status was observed.",
                process_id=run_id, parent_event_id=submitted_id,
            )
            return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ask the active LLM for haikus with a configured wait between requests.")
    parser.add_argument("--url", required=True, help="LLM server base URL, e.g. http://host:27770")
    parser.add_argument("--output", type=Path, default=Path("tmp/haiku"))
    parser.add_argument("--count", type=int, default=DSnakeLab.HAIKU_COUNT,
                        help="Override DSnakeLab.HAIKU_COUNT; 0 repeats until stopped")
    args = parser.parse_args(argv)
    if args.count < 0:
        parser.error("--count must be zero or positive")
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
                run(LLM(args.url), output, db, args.count)
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
