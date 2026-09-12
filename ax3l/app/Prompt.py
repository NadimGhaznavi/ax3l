import json


class Prompt:
    def __init__(self, content: str):
        self._content = content

    def to_json(self) -> str:
        return json.dumps({"role": "user", "content": self._content}, ensure_ascii=False)

    def to_md(self) -> str:
        return self._content
