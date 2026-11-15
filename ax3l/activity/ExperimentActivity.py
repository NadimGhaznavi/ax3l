"""Project checklist time, token usage, and current images from logged work."""

from datetime import datetime
import json

from ax3l.constants.DEventCategory import DEventCategory as Events
from ax3l.constants.DSimulationAnalysis import DSimulationAnalysis


def item_activity(events: list[dict]) -> dict[tuple[str, str], dict]:
    """Count complete conversations, including tool turns, once per work item."""
    items, conversations, tasks = {}, {}, {}
    now = events[0]["observed_at"] if events else None

    def item(key: tuple[str, str]) -> dict:
        return items.setdefault(key, dict(seconds=0.0, tokens=0, image_event_id=None))

    def finish_task(process_id: str, ended: datetime) -> None:
        key, started = tasks.pop(process_id)
        item(key)["seconds"] += (ended - started).total_seconds()

    for event in events:
        process_id, name, timestamp = event["process_id"], event["name"], event["occurred_at"]
        if name == Events.SnakeLab.ANALYSIS_TASK:
            task = event["task"]
            if task["phase"] == "preparing":
                if process_id in tasks:
                    finish_task(process_id, timestamp)
                key = (process_id, task["section"])
                item(key)
                tasks[process_id] = (key, timestamp)
            elif task["phase"] in ("saved", "failed", "stopped") and process_id in tasks:
                finish_task(process_id, timestamp)
        elif name == Events.Conversation.STARTED:
            conversations[event["event_id"]] = dict(started=timestamp, ended=None, key=None)
        elif event["parent_event_id"] in conversations:
            conversation = conversations[event["parent_event_id"]]
            if name == Events.Conversation.PROMPT and event["parameter"] is not None:
                if event["parameter"] == "simulation_summary":
                    key = tasks[process_id][0]
                else:
                    key = (process_id, event["parameter"])
                conversation["key"] = key
                activity = item(key)
                if event["source_name"] == "AnalyzeSimulation":
                    activity["image_event_id"] = event["event_id"]
            elif name == Events.Conversation.RESPONSE:
                activity = item(conversation["key"])
                tokens = event["tokens"]
                activity["tokens"] = (activity["tokens"] + tokens
                                      if activity["tokens"] is not None and tokens is not None else None)
            elif name == Events.Conversation.ENDED:
                conversation["ended"] = timestamp

    for key, started in tasks.values():
        item(key)["seconds"] += (now - started).total_seconds()
    for conversation in conversations.values():
        key = conversation["key"]
        # Analysis tasks already include chart preparation and their conversation.
        if key is not None and key[1] not in DSimulationAnalysis.SECTIONS:
            item(key)["seconds"] += ((conversation["ended"] or now) - conversation["started"]).total_seconds()
    return items


def choice_activity(events: list[dict]) -> dict[str, dict]:
    """Keep the time and usage of each setup step separate."""
    choices, conversations, active = {}, {}, {}
    config, chat, llm, tool = Events.Configuration, Events.Conversation, Events.LLM, Events.Tool

    def choice(parameter):
        return choices.setdefault(parameter, dict(steps=[], image_event_id=None))

    def start(parameter, label, at):
        if parameter in active:
            active[parameter].update(state="Interrupted", seconds=None)
        step = dict(label=label, started=at, seconds=None, state="Running",
                    input_tokens=None, output_tokens=None)
        choice(parameter)["steps"].append(step)
        active[parameter] = step

    def finish(parameter, state, at, usage=None):
        step = active.pop(parameter, None)
        if step is not None:
            usage = usage or {}
            step.update(state=state, seconds=(at - step["started"]).total_seconds(),
                        input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"))

    for event in events:
        name, at, detail = event["name"], event["occurred_at"], event["detail"]
        parent, parameter = event["parent_event_id"], event["parameter"]
        if name == config.CHART_STARTED:
            start(parameter, f"Render {detail.lower()} chart", at)
        elif name == config.CHART_FINISHED:
            finish(parameter, detail, at)
        elif name == chat.PROMPT and parameter is not None:
            conversations[parent] = parameter
            if event["has_image"]:
                choice(parameter)["image_event_id"] = event["event_id"]
        elif parent in conversations:
            parameter = conversations[parent]
            if name == llm.REQUEST_STARTED:
                start(parameter, "Qwen request", at)
            elif name == chat.RESPONSE:
                finish(parameter, "Complete", at, json.loads(detail) if detail else None)
            elif name == tool.STARTED:
                function = json.loads(detail)["function"]
                label = {"data_tool": "Read data", "kb_tool": "Read guide"}.get(function["name"], "Submit choice")
                if function["name"] in ("data_tool", "kb_tool"):
                    arguments = json.loads(function["arguments"])
                    path = arguments.get("url") if isinstance(arguments, dict) else None
                    if isinstance(path, str) and len(path) <= 60:
                        label += f" {path}"
                start(parameter, label, at)
            elif name == tool.COMPLETED:
                finish(parameter, "Rejected" if detail == "rejected" else "Complete", at)
            elif name in (llm.REQUEST_FAILED, tool.FAILED):
                finish(parameter, "Failed", at)
            elif name == chat.ENDED:
                finish(parameter, "Stopped", at)

    if events:
        now = events[0]["observed_at"]
        for step in active.values():
            step["seconds"] = (now - step["started"]).total_seconds()
    return choices
