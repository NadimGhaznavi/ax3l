"""Run from the checkout: python3 -m ax3l.app.snakelab.main-loop --url URL."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import traceback
from uuid import uuid4

from ax3l.app.DbMgr import DbMgr

from ax3l.app.snakelab.prompts.GenerateHaiku import GenerateHaiku
from ax3l.interface.LLM import LLM


def run(llm: LLM, output: Path, db: DbMgr, count: int = 0) -> None:
    process_id = str(uuid4())
    print(f"Conversation: {process_id}", flush=True)
    conversation_id = db.log(
        "conversation_started", "Conversation", "INFO",
        f"Haiku conversation started with {llm.url}. Output: {output.resolve()}",
        process_id=process_id,
    )
    outcome = "Completed requested haiku turns."
    level = "INFO"
    try:
        prompt = GenerateHaiku()
        turn = 0
        while count == 0 or turn < count:
            turn += 1
            prefix = output / f"{turn:04d}"
            payload = json.dumps({
                "messages": [json.loads(prompt.to_json())],
                "stream": False,
            }, ensure_ascii=False).encode("utf-8")
            prefix.with_suffix(".request.json").write_bytes(payload)
            print(f"{datetime.now(timezone.utc).isoformat()} Request {turn}: {llm.url}", flush=True)
            prompt_id = db.log(
                "prompt_sent", "Conversation", "INFO", prompt.to_md(),
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
            prefix.with_suffix(".response.body").write_bytes(body)
            prefix.with_suffix(".response.headers").write_text(
                f"HTTP status: {status}\n{headers}", encoding="utf-8"
            )
            response_text = body.decode("utf-8", errors="backslashreplace")
            print(f"HTTP status: {status}\n{headers}", flush=True)
            print(response_text, flush=True)
            if status >= 400:
                db.log(
                    "llm_request_failed", "LLM", "ERROR",
                    f"HTTP {status}\n{response_text}",
                    process_id=process_id, parent_event_id=prompt_id,
                )
                raise RuntimeError(f"LLM returned HTTP {status}; see {prefix}.response.body")
            reply_id = db.log(
                "reply_received", "Conversation", "INFO", response_text,
                process_id=process_id, parent_event_id=prompt_id,
            )
            if count == 0 or turn < count:
                wait_id = db.log(
                    "wait_started", "Process", "INFO", "Waiting five seconds before the next prompt.",
                    process_id=process_id, parent_event_id=reply_id,
                )
                time.sleep(5)
                db.log(
                    "wait_ended", "Process", "INFO", "Five-second wait completed.",
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
            "conversation_ended", "Conversation", level, outcome,
            process_id=process_id, parent_event_id=conversation_id,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask the active LLM for a haiku every five seconds.")
    parser.add_argument("--url", required=True, help="LLM server base URL, e.g. http://host:27770")
    parser.add_argument("--output", type=Path, default=Path("tmp/haiku"))
    parser.add_argument("--count", type=int, default=0, help="Number of requests; 0 repeats until Ctrl-C")
    args = parser.parse_args()
    if args.count < 0:
        parser.error("--count must be zero or positive")
    output = args.output / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    output.mkdir(parents=True)
    print(f"Capturing output in {output.resolve()}", flush=True)
    with (output / "run.log").open("w", encoding="utf-8", buffering=1) as log:
        with redirect_stdout(log), redirect_stderr(log):
            try:
                db = DbMgr()
                try:
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
