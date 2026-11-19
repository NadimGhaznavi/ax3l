"""Run one conversation until its bound MCP tool accepts a result."""

import asyncio
import json
from math import ceil
from time import monotonic

from uuid import uuid4

from ax3l.constants.DAx3l import DAx3l
from ax3l.constants.DChoice import DECISION_GRACE_SECONDS
from ax3l.constants.DEventCategory import DEventCategory as Events


class DecisionTimeExpired(Exception):
    """The decision budget and grace period have elapsed."""


async def _before_deadline(operation, deadline: float | None):
    """Bound read-only work; submissions must finish without cancellation."""
    if deadline is None:
        return await operation()
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise DecisionTimeExpired()
    window = asyncio.timeout(remaining)
    try:
        async with window:
            return await operation()
    except TimeoutError as error:
        if window.expired():
            raise DecisionTimeExpired() from error
        raise


def _time_reminder(deadline: float, conversation_deadline: float | None = None, *,
                   reset_on_expiry: bool = False) -> dict[str, str]:
    action = ("restart from the initial prompt in a fresh conversation, discarding the tentative parameter "
              "selection and all previous messages" if reset_on_expiry else
              "run the saved unique configuration and continue the normal experiment cycle")
    now = monotonic()
    if conversation_deadline is not None and now >= deadline:
        seconds = max(0, ceil(conversation_deadline - now))
        minutes, remainder = divmod(seconds, 60)
        return {"role": "user", "content":
                f"The decision budget has expired. Grace time remaining: {minutes:02}:{remainder:02} "
                f"({seconds} seconds). Decide now; when the grace period ends, Ax3l will {action}."}
    seconds = max(0, ceil(deadline - now))
    minutes, remainder = divmod(seconds, 60)
    detail = ("Make your next decision promptly using the evidence gathered." if seconds else
              "The advisory budget has elapsed. Make your next decision now using the evidence gathered.")
    if conversation_deadline is not None:
        detail += (f" A further {DECISION_GRACE_SECONDS // 60}-minute grace period follows this budget; "
                   f"then Ax3l will {action} if you have not decided.")
    return {"role": "user", "content":
            f"Decision time remaining: {minutes:02}:{remainder:02} ({seconds} seconds). {detail}"}


async def converse(llm, output, db, tools, prompts, *, parameter: str | None = None,
                   process_id: str | None = None, decision_deadline: float | None = None,
                   conversation_deadline: float | None = None, reset_on_expiry: bool = False) -> dict:
    process_id = process_id or str(uuid4())
    print(f"Conversation: {process_id}", flush=True)
    conversation_id = db.log(Events.Conversation.STARTED, Events.Conversation.CATEGORY,
                             "INFO", f"Conversation started with {llm.url}.", process_id=process_id)

    def log(category, name, content, level="INFO", *, source_name=None):
        return db.log(name, category.CATEGORY, level, content, process_id=process_id,
                      parent_event_id=conversation_id, source_name=source_name,
                      parameter=parameter if category is Events.Conversation and name == Events.Conversation.PROMPT else None)

    outcome, level = "Tool result accepted.", "INFO"
    try:
        tool_name = tools.definition["function"]["name"]
        definitions = {definition["function"]["name"]: definition["function"]
                       for definition in tools.definitions}
        messages = [json.loads(prompt.to_json()) for prompt in prompts]
        for prompt, message in zip(prompts, messages):
            log(Events.Conversation, Events.Conversation.PROMPT, json.dumps(message, ensure_ascii=False),
                source_name=prompt.source_name)
        if decision_deadline is not None:
            reminder = _time_reminder(decision_deadline, conversation_deadline, reset_on_expiry=reset_on_expiry)
            messages.append(reminder)
            log(Events.Conversation, Events.Conversation.PROMPT, json.dumps(reminder, ensure_ascii=False),
                source_name="ToolConversation")
        turn = 0
        while True:
            turn += 1
            payload = json.dumps({"messages": messages, "tools": tools.definitions,
                                  "tool_choice": "required", "parallel_tool_calls": False,
                                  "stream": False}, ensure_ascii=False).encode()
            prefix = output / f"{process_id}-{conversation_id}-{turn:04d}"
            if DAx3l.RAW_LOGS_ENABLED:
                prefix.with_suffix(".request.json").write_bytes(payload)
            log(Events.LLM, Events.LLM.REQUEST_STARTED, f"Inference request {turn}.")
            try:
                def request_inference():
                    if conversation_deadline is None:
                        return asyncio.to_thread(llm.complete, payload)
                    return asyncio.to_thread(llm.complete, payload,
                                             timeout_seconds=max(0, conversation_deadline - monotonic()) + 1)

                status, headers, body = await _before_deadline(request_inference, conversation_deadline)
                if DAx3l.RAW_LOGS_ENABLED:
                    prefix.with_suffix(".response.body").write_bytes(body)
                    prefix.with_suffix(".response.headers").write_text(f"HTTP status: {status}\n{headers}")
                if status >= 400:
                    raise RuntimeError(f"HTTP {status}: {body.decode(errors='replace')}")
            except DecisionTimeExpired:
                raise
            except Exception as error:
                log(Events.LLM, Events.LLM.REQUEST_FAILED, str(error), "ERROR")
                raise
            reply_id = log(Events.Conversation, Events.Conversation.RESPONSE, body.decode(errors="backslashreplace"))
            choice = json.loads(body)["choices"][0]
            reply = choice["message"]
            calls = reply.get("tool_calls", [])
            if len(calls) != 1 or calls[0]["function"]["name"] not in definitions:
                names = [call["function"]["name"] for call in calls]
                raise ValueError(
                    f"Expected exactly one {' or '.join(definitions)} tool call; received {names!r}, "
                    f"finish_reason={choice.get('finish_reason')!r}. See reply event {reply_id}."
                )
            call = calls[0]
            called_name = call["function"]["name"]
            argument_names = set(definitions[called_name]["parameters"]["properties"])
            arguments = json.loads(call["function"]["arguments"])
            messages.append(reply)
            log(Events.Tool, Events.Tool.STARTED, json.dumps(call))
            try:
                if not isinstance(arguments, dict) or set(arguments) != argument_names:
                    result = {"status": "rejected", "code": "invalid_arguments",
                              "source_name": "ToolConversation",
                              "prompt": {"role": "user", "content":
                                  f"Call {called_name} with exactly these fields: "
                                  + ", ".join(sorted(argument_names)) + "."}}
                else:
                    if called_name == "kb_tool":
                        result = await _before_deadline(lambda: tools.reference(arguments), conversation_deadline)
                    elif called_name == "data_tool":
                        result = await _before_deadline(lambda: tools.data(arguments), conversation_deadline)
                    else:
                        if conversation_deadline is not None and monotonic() >= conversation_deadline:
                            raise DecisionTimeExpired()
                        result = (await tools.submit(arguments) if called_name == tool_name else
                                  await tools.submit(arguments, name=called_name))
                if result["status"] not in ("ok", "rejected"):
                    raise RuntimeError(f"Tool submission failed: {result}")
            except DecisionTimeExpired:
                raise
            except Exception as error:
                log(Events.Tool, Events.Tool.FAILED, str(error), "ERROR")
                raise
            log(Events.Tool, Events.Tool.COMPLETED, json.dumps(result))
            if result["status"] == "ok" and called_name not in ("kb_tool", "data_tool"):
                return result
            # Explicit validation rejections are safe to correct. Transport failures are not retried.
            messages.append({"role": "tool", "tool_call_id": call["id"],
                             "content": result["page"] if result["status"] == "ok" else "Rejected."})
            if result["status"] == "rejected":
                feedback = result["prompt"]
                messages.append(feedback)
                log(Events.Conversation, Events.Conversation.PROMPT, json.dumps(feedback, ensure_ascii=False),
                    source_name=result.get("source_name", "ToolConversation"))
            if called_name == "data_tool" and decision_deadline is not None:
                reminder = _time_reminder(decision_deadline, conversation_deadline, reset_on_expiry=reset_on_expiry)
                messages.append(reminder)
                log(Events.Conversation, Events.Conversation.PROMPT, json.dumps(reminder, ensure_ascii=False),
                    source_name="ToolConversation")
    except DecisionTimeExpired:
        outcome = ("Decision budget and grace period expired; restarting from the initial prompt in a fresh conversation."
                   if reset_on_expiry else
                   "Decision budget and grace period expired; submitting the saved unique configuration.")
        raise
    except (KeyboardInterrupt, asyncio.CancelledError):
        outcome = "Stopped by user."
        raise
    except BaseException as error:
        outcome, level = f"Conversation stopped: {type(error).__name__}: {error}", "ERROR"
        raise
    finally:
        log(Events.Conversation, Events.Conversation.ENDED, outcome, level)
