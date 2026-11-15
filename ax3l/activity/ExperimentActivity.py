"""Project checklist time, token usage, and current images from logged work."""

from datetime import datetime

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
