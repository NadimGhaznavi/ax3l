"""Render separate result evaluation and configuration prompts for each view."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from ax3l.constants.DViewConversation import DViewConversation
from ax3l.entities.ExperimentView import ExperimentView
from ax3l.presentation.ComparisonImage import comparison_image
from ax3l.presentation.GoldenRunScoreImage import golden_run_score_image


class ViewPrompts:
    def __init__(self):
        self._templates = Environment(
            loader=FileSystemLoader(Path(__file__).with_name("prompts")),
            undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True,
        )

    def render(self, view: ExperimentView, context: dict) -> str | list[dict]:
        image_marker = "{{ golden_run_score_image }}"
        prompt = self._templates.get_template(f"selections/{view.name}.md").render(
            **context, golden_run_score_image=image_marker,
        )
        submission = self._templates.get_template("selections/proposal-submission.md").render(
            hypothesis_max_length=DViewConversation.HYPOTHESIS_MAX_LENGTH,
        )
        prompt += "\n\n" + submission
        if view.name == "architecture":
            before, after = prompt.split(image_marker)
            return [dict(type="text", text=before), dict(type="image_url", image_url=dict(
                url=golden_run_score_image(context["golden_run_episodes"]),
            )), dict(type="text", text=after)]
        return prompt

    def render_evaluation(self, view: ExperimentView, context: dict) -> list[dict]:
        prompt = self._templates.get_template(f"evaluations/{view.name}.md").render(
            **context, observations_max_length=DViewConversation.OBSERVATIONS_MAX_LENGTH,
        )
        return [dict(type="text", text=prompt), dict(type="image_url", image_url=dict(
            url=comparison_image(view, context["reference_run_id"], context["latest_run_id"]),
        ))]
