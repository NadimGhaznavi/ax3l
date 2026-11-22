"""Render UTF-8 Markdown templates with strict named values and JSON encoding."""

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from ax3l.activity.PresentationValues import presentation_values


class MarkdownTemplates:
    def __init__(self, root: Path):
        self._environment = Environment(
            loader=FileSystemLoader(root), undefined=StrictUndefined, autoescape=False,
            trim_blocks=True, lstrip_blocks=True,
            cache_size=0,
        )
        self._environment.filters["json"] = self._json

    @staticmethod
    def _json(value, compact: bool = True) -> str:
        options = {"separators": (",", ":")} if compact else {}
        return json.dumps(presentation_values(value), ensure_ascii=False, allow_nan=False, **options)

    def render(self, name: str, **values) -> str:
        return self._environment.get_template(name).render(**values).strip()
