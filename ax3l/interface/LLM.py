from collections.abc import Callable
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from jsonschema import Draft202012Validator

from ax3l.constants.DAx3l import DAx3l
from ax3l.entities.LLMReply import LLMReply


_CHUNK = Draft202012Validator({
    "type": "object", "required": ["choices"], "properties": {
        "choices": {"type": "array", "maxItems": 1, "items": {
            "type": "object", "required": ["index", "delta"], "properties": {
                "index": {"const": 0},
                "delta": {"type": "object", "properties": {
                    "role": {"type": "string"},
                    "content": {"type": ["string", "null"]},
                    "reasoning_content": {"type": ["string", "null"]},
                    "tool_calls": {"type": ["array", "null"], "items": {
                        "type": "object", "required": ["index"], "properties": {
                            "index": {"type": "integer", "minimum": 0},
                            "function": {"type": "object", "additionalProperties": {"type": "string"}},
                        },
                    }},
                }},
            },
        }},
    },
})


def _nonfinite(value):
    raise ValueError(f"Nonfinite JSON number: {value}")


def _read_stream(response, on_progress: Callable[[dict], None]) -> bytes:
    """Read SSE frames without waiting for the HTTP response to close."""
    reply = LLMReply()
    data = []
    while True:
        line = response.readline()
        if not line:
            raise ConnectionError("LLM stream ended before [DONE].")
        line = line.rstrip(b"\r\n")
        if line.startswith(b"data:"):
            value = line[5:]
            data.append(value[1:] if value.startswith(b" ") else value)
        elif not line and data:
            value = b"\n".join(data)
            data = []
            if value == b"[DONE]":
                return json.dumps(reply.response, ensure_ascii=False, allow_nan=False).encode()
            chunk = json.loads(value, parse_constant=_nonfinite)
            if isinstance(chunk, dict) and "error" in chunk:
                raise RuntimeError(f"LLM stream error: {json.dumps(chunk['error'])}")
            _CHUNK.validate(chunk)
            reply.append(chunk)
            on_progress(reply.response)


class LLMTimeoutError(TimeoutError):
    """An inference request timed out before a usable response arrived."""


class LLM:
    """Send inference requests, assembling streamed replies when requested."""

    def __init__(self, base_url: str):
        self.url = base_url.rstrip("/") + "/v1/chat/completions"

    def complete(self, payload: bytes, *, timeout_seconds: float | None = None,
                 on_progress: Callable[[dict], None] | None = None) -> tuple[int, str, bytes]:
        request = Request(
            self.url, data=payload, headers={"Content-Type": "application/json"}
        )
        try:
            try:
                response = urlopen(request, timeout=DAx3l.HTTP_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds)
            except HTTPError as error:
                response = error
            with response:
                if on_progress is None or response.status >= 400:
                    body = response.read()
                else:
                    if response.headers.get_content_type() != "text/event-stream":
                        raise ValueError("Expected a text/event-stream inference response.")
                    body = _read_stream(response, on_progress)
                return response.status, str(response.headers), body
        except TimeoutError as error:
            raise LLMTimeoutError(f"Inference request to {self.url} timed out.") from error
        except URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise LLMTimeoutError(f"Inference request to {self.url} timed out.") from error
            raise
