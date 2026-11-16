"""Ask Qwen which parameter to change or whether to run a unique draft."""

import json

from ax3l.app.Prompt import Prompt
from ax3l.app.snakelab.ParameterSpace import parameter_values
from ax3l.constants.DChoice import CHOICE_LABELS
from ax3l.entities.ConfigurationDraft import ConfigurationDraft, PARAMETER_ORDER


class ConfigurationNextStep(Prompt):
    def __init__(self, draft: ConfigurationDraft):
        choices = {parameter: dict(label=CHOICE_LABELS[parameter], values=parameter_values(draft.config, parameter))
                   for parameter in PARAMETER_ORDER}
        if draft.phase == "reviewing":
            instruction = ("The current configuration is unique. Use run_simulation to run it, "
                           "or select_parameter to change another setting or the same setting again.")
        elif draft.selections:
            instruction = ("The current configuration already exists in the simulation database. "
                           "Choose which setting to change using select_parameter; this draft cannot run yet.")
        else:
            instruction = ("The draft starts with baseline values from the golden configuration. "
                           "Research which setting would be best to tweak, then choose it using select_parameter.")
        super().__init__(
            instruction + " Paired settings are changed together. Other values stay in the draft. "
            "After each submitted change, Ax3l checks the complete configuration for uniqueness. "
            "You choose which settings to adjust and when to run; there is no required parameter order. "
            "Use data_tool at / for measured reference runs, /golden/notes for observations, "
            "or /draft for the current values.\n\n"
            f"Available parameter keys and current values:\n```json\n{json.dumps(choices, allow_nan=False)}\n```"
        )
