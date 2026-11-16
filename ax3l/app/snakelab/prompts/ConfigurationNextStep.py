"""Ask Qwen which parameter to change or whether to run a unique draft."""

import json

from ax3l.app.Prompt import Prompt
from ax3l.app.snakelab.ParameterSpace import parameter_values
from ax3l.constants.DChoice import CHOICE_LABELS, PARAMETER_SELECTION_SECONDS, UNIQUE_CONFIG_GRACE_SECONDS
from ax3l.entities.ConfigurationDraft import ConfigurationDraft, PARAMETER_ORDER


class ConfigurationNextStep(Prompt):
    def __init__(self, draft: ConfigurationDraft):
        choices = {parameter: dict(label=CHOICE_LABELS[parameter], values=parameter_values(draft.config, parameter))
                   for parameter in PARAMETER_ORDER if parameter not in draft.selections}
        if draft.phase == "reviewing" and not choices:
            instruction = ("All eligible settings have been changed and the configuration is unique. "
                           "Use run_simulation to run it; no unused settings remain.")
        elif draft.phase == "reviewing":
            instruction = ("The current configuration is unique. Use run_simulation to run it, "
                           "or select_parameter to change an unused setting.")
        elif draft.selections:
            instruction = ("The current configuration already exists in the simulation database. "
                           "Choose which setting to change using select_parameter; this draft cannot run yet.")
        else:
            instruction = ("The draft starts with baseline values from the golden configuration. "
                           "Research which setting would be best to tweak, then choose it using select_parameter.")
        super().__init__(
            instruction + f" Aim to make this decision within {PARAMETER_SELECTION_SECONDS // 60} minutes. "
            "This is an advisory time budget; after each data_tool request you will receive the remaining time. "
            "The countdown continues while choosing a value. An accepted unique change starts a fresh five-minute "
            "budget to choose another parameter or run the configuration. "
            f"Once a unique draft is available, an expired budget gives you {UNIQUE_CONFIG_GRACE_SECONDS // 60} extra "
            "minutes; then Ax3l submits the saved unique configuration and continues the normal experiment cycle. "
            "Paired settings are changed together. Other values stay in the draft. "
            "Each setting may be selected only once per experiment. Once selected, you must change at least one "
            "of its values; keeping the current values is not allowed. "
            "After each submitted change, Ax3l checks the complete configuration for uniqueness. "
            "Duplicate values must be revised within the selected setting before you can choose another setting. "
            "You choose which settings to adjust and when to run; there is no required parameter order. "
            "Use data_tool at / for measured reference runs or /draft for the current values.\n\n"
            f"Available parameter keys and current values:\n```json\n{json.dumps(choices, allow_nan=False)}\n```"
        )
