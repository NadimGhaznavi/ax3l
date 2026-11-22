"""Ask Qwen which parameter to change or whether to run a unique draft."""

from ax3l.app.Prompt import Prompt
from ax3l.app.snakelab.ParameterSpace import parameter_values
from ax3l.constants.DChoice import CHOICE_LABELS
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
from ax3l.presentation.snakelab.Templates import templates


class ConfigurationNextStep(Prompt):
    def __init__(self, draft: ConfigurationDraft, parameters: list[str]):
        choices = {parameter: dict(label=CHOICE_LABELS[parameter], values=parameter_values(draft.config, parameter))
                   for parameter in parameters}
        if draft.phase == "reviewing" and not choices:
            action = "run"
        elif draft.phase == "reviewing":
            action = "review"
        elif draft.selections:
            action = "revise"
        else:
            action = "select"
        super().__init__(templates.render("prompts/next_step.md.jinja", action=action,
                                         choices=choices, seed_selected="seed" in draft.selections))
