"""Convert JSON settings and record lists into compact Markdown tables."""

from html import escape
import json
import re
from typing import Any

from ax3l.activity.PresentationValues import presentation_values


def _text(value: Any) -> str:
    if isinstance(value, dict) and value:
        return "; ".join(f"{key.replace('_', ' ')}: {_text(item)}" for key, item in value.items())
    if isinstance(value, list) and value:
        return ", ".join(_text(item) for item in value)
    if isinstance(value, str):
        return value or '""'
    return json.dumps(presentation_values(value), ensure_ascii=False, allow_nan=False)


def _cell(value: Any) -> str:
    value = _text(value)
    value = escape(value, quote=False).replace("\r\n", "\n").replace("\n", " ↵ ")
    return re.sub(r"([\\`*_\[\]|])", r"\\\1", value)


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    return "\n".join("| " + " | ".join(_cell(value) for value in row) + " |"
                     for row in [headers, ["---"] * len(headers), *rows])


def _fields(value: dict, prefix: str = "") -> list[list[Any]]:
    rows = []
    for key, item in value.items():
        label = f"{prefix} / {key}" if prefix else key
        label = label.replace("_", " ")
        if isinstance(item, dict) and item:
            rows.extend(_fields(item, label))
        else:
            rows.append([label, item])
    return rows


def _records(value: dict, prefix: str = "") -> list[tuple[str, dict]]:
    rows = []
    for key, record in value.items():
        label = f"{prefix} / {key}" if prefix else key
        if all(isinstance(item, dict) and item for item in record.values()):
            rows.extend(_records(record, label))
        else:
            rows.append((label, record))
    return rows


def json_markdown(value: Any) -> str:
    """Handle the nested settings, scalar lists, and record lists used in reports."""
    if isinstance(value, dict) and value:
        records = list(value.values())
        if len(records) > 1 and all(isinstance(record, dict) and record for record in records):
            rows = _records(value)
            keys = list(rows[0][1])
            if all(record.keys() == rows[0][1].keys() for _, record in rows):
                if any(all(record[field] == name for name, record in rows) for field in keys):
                    return _table([key.replace("_", " ") for key in keys],
                                  [[record[field] for field in keys] for _, record in rows])
                return _table(["Field", *(key.replace("_", " ") for key in keys)],
                              [[name.replace("_", " "), *(record[field] for field in keys)]
                               for name, record in rows])
        simple = {key: item for key, item in value.items() if not isinstance(item, (dict, list)) or not item}
        sections = [_table(["Field", "Value"], _fields(simple))] if simple else []
        for key, item in value.items():
            if isinstance(item, (dict, list)) and item:
                content = json_markdown(item) if isinstance(item, list) or all(
                    isinstance(record, dict) and record for record in item.values()
                ) else _table(["Field", "Value"], _fields(item))
                sections.append(f"### {_cell(key.replace('_', ' '))}\n\n{content}")
        return "\n\n".join(sections)
    if isinstance(value, list) and value:
        if all(isinstance(item, dict) and item for item in value):
            records = [dict((label, cell) for label, cell in _fields(item)) for item in value]
            columns = list(dict.fromkeys(key for record in records for key in record))
            return _table(columns, [[record.get(key, "—") for key in columns] for record in records])
        return _table(["Value"], [[item] for item in value])
    return _cell(value)
