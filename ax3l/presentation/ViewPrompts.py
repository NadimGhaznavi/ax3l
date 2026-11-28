"""Render separate result evaluation and configuration prompts for each view."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from ax3l.constants.DViewConversation import DViewConversation
from ax3l.entities.ExperimentView import ExperimentView
from ax3l.presentation.RunComparisonImage import run_comparison_image


class ViewPrompts:
    def __init__(self):
        self._templates = Environment(
            loader=FileSystemLoader(Path(__file__).with_name("prompts")),
            undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True,
        )

    def render(self, view: ExperimentView, context: dict, *, no_history: bool = False,
               duplicate: bool = False) -> list[dict]:
        folder = "selections-no-history" if no_history else "selections"
        prompt = self._templates.get_template(f"{folder}/{view.name}.md").render(**context)
        if duplicate:
            notice = self._templates.get_template("common/duplicate-configuration.md").render(**context)
            prompt = notice.strip() + "\n\n" + prompt
        image = run_comparison_image(view, context["reference_episodes"],
                                     None if no_history else context["latest_episodes"])
        return [dict(type="text", text=prompt), dict(type="image_url", image_url=dict(url=image))]

    def render_evaluation(self, view: ExperimentView, context: dict) -> list[dict]:
        prompt = self._templates.get_template(f"evaluations/{view.name}.md").render(
            **context, observations_max_length=DViewConversation.OBSERVATIONS_MAX_LENGTH,
        )
        image = run_comparison_image(view, context["reference_episodes"], context["latest_episodes"])
        return [dict(type="text", text=prompt), dict(type="image_url", image_url=dict(url=image))]
