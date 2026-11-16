"""Ask which saved setting to revise after a duplicate configuration."""

import json

from ax3l.app.Prompt import Prompt
from ax3l.app.snakelab.ParameterSpace import parameter_values
from ax3l.constants.DChoice import CHOICE_LABELS
from ax3l.entities.ConfigurationDraft import ConfigurationDraft, PARAMETER_ORDER


class NoDupes(Prompt):
    def __init__(self, draft: ConfigurationDraft):
        choices = {parameter: dict(label=CHOICE_LABELS[parameter], values=parameter_values(draft.config, parameter))
                   for parameter in PARAMETER_ORDER}
        super().__init__(
            "The complete configuration already exists in the simulation database. "
            "Choose which setting to revise using select_parameter. "
            "Ax3l will open that setting's value conversation, then check the complete configuration again. "
            "Paired settings are revised together. Other saved values stay in the draft. "
            "Use data_tool at /draft for saved values or / for reference runs.\n\n"
            f"Available parameter keys and current values:\n```json\n{json.dumps(choices, allow_nan=False)}\n```"
        )
