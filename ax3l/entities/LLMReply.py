"""Accumulate validated chat-completion deltas into one assistant reply."""


class LLMReply:
    def __init__(self):
        self.response: dict = {"choices": []}
        self._message: dict = {}
        self._choice: dict = {"index": 0, "message": self._message}
        self._calls: dict[int, dict] = {}

    def append(self, chunk: dict) -> None:
        self.response.update({key: value for key, value in chunk.items()
                              if key != "choices" and value is not None})
        if "object" in chunk:
            self.response["object"] = "chat.completion"
        for choice in chunk["choices"]:
            self.response["choices"] = [self._choice]
            self._choice.update({key: value for key, value in choice.items() if key != "delta"})
            delta = choice["delta"]
            self._message.update({key: value for key, value in delta.items()
                                  if key not in ("content", "reasoning_content", "tool_calls")})
            for field in ("content", "reasoning_content"):
                if delta.get(field) is not None:
                    self._message[field] = self._message.get(field, "") + delta[field]
            for fragment in delta.get("tool_calls") or []:
                call = self._calls.setdefault(fragment["index"], {})
                call.update({key: value for key, value in fragment.items()
                             if key not in ("index", "function") and value is not None})
                for field, value in fragment.get("function", {}).items():
                    function = call.setdefault("function", {})
                    function[field] = function.get(field, "") + value
                self._message["tool_calls"] = [self._calls[index] for index in sorted(self._calls)]
