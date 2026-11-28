"""Keep one durable EventLog capture of an in-flight inference response."""

from datetime import datetime, timezone
import json
from time import monotonic

from ax3l.constants.DEventCategory import DEventCategory as Events
from ax3l.constants.DViewConversation import DViewConversation
from ax3l.interface.database.EventLogDb import EventLogDb


class LLMResponseCapture:
    def __init__(self, events: EventLogDb, request_event_id: int, *, process_id: str,
                 parent_event_id: int, source_name: str, parameter: str):
        self._events = events
        self._response: dict = {"choices": []}
        self._capture = dict(status="in_progress", request_event_id=request_event_id,
                             started_at=datetime.now(timezone.utc).isoformat(),
                             received_chunks=0, last_chunk_at=None)
        self._last_saved = monotonic()
        self._event_id = events.log(
            Events.LLM.RESPONSE_CAPTURED, Events.LLM.CATEGORY, "INFO", self._content(),
            process_id=process_id, parent_event_id=parent_event_id,
            source_name=source_name, parameter=parameter)

    def _content(self) -> str:
        return json.dumps(dict(self._response, capture=self._capture), ensure_ascii=False, allow_nan=False)

    def _save(self) -> None:
        self._events.update_content(self._event_id, self._content())
        self._last_saved = monotonic()

    def receive(self, response: dict) -> None:
        self._response = response
        self._capture["received_chunks"] += 1
        self._capture["last_chunk_at"] = datetime.now(timezone.utc).isoformat()
        if (self._capture["received_chunks"] == 1 or
                monotonic() - self._last_saved >= DViewConversation.CAPTURE_INTERVAL_SECONDS):
            self._save()

    def __enter__(self) -> "LLMResponseCapture":
        return self

    def __exit__(self, error_type, error, traceback) -> None:
        self._capture["status"] = "completed" if error_type is None else "interrupted"
        if error_type is not None:
            self._capture["error"] = f"{error_type.__name__}: {error}"
        self._save()
