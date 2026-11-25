"""Prepare JSON values for display without changing their stored precision."""

from typing import Any


def presentation_values(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 5)
    if isinstance(value, dict):
        return {key: presentation_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [presentation_values(item) for item in value]
    return value
