"""Prepare captured LLM replies for presentation without changing stored data."""

import json
from typing import Any


def reply_content(response: dict[str, Any]) -> str:
    return response["choices"][0]["message"]["content"]


def fields(value: Any, path: str = "") -> list[tuple[str, str]]:
    """Keep every response field, identifying nested values by their full path."""
    if isinstance(value, dict) and value:
        return [row for key, item in value.items()
                for row in fields(item, f"{path}.{key}" if path else key)]
    if isinstance(value, list) and value:
        return [row for index, item in enumerate(value)
                for row in fields(item, f"{path}[{index}]")]
    return [(path, value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))]
