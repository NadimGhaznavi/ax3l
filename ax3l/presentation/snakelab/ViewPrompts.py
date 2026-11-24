"""Load and render the four model-facing view templates."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from ax3l.entities.ExperimentView import ExperimentView


class ViewPrompts:
    def __init__(self):
        self._templates = Environment(
            loader=FileSystemLoader(Path(__file__).with_name("prompts")),
            undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True,
        )

    def render(self, view: ExperimentView, context: dict) -> str:
        return self._templates.get_template(f"{view.name}.md").render(**context)
