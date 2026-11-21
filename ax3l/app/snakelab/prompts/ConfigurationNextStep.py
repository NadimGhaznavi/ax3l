"""Ask Qwen which parameter to change or whether to run a unique draft."""

import json

from ax3l.app.Prompt import Prompt
from ax3l.app.snakelab.ParameterSpace import parameter_values
from ax3l.constants.DChoice import CHOICE_LABELS, PARAMETER_SELECTION_SECONDS, DECISION_GRACE_SECONDS
from ax3l.entities.ConfigurationDraft import ConfigurationDraft


class ConfigurationNextStep(Prompt):
    def __init__(self, draft: ConfigurationDraft, parameters: list[str]):
        choices = {parameter: dict(label=CHOICE_LABELS[parameter], values=parameter_values(draft.config, parameter))
                   for parameter in parameters}
        if draft.phase == "reviewing" and not choices:
            instruction = ("No unused settings with untested changes remain and the configuration is unique. "
                           "Use run_simulation to run it.")
        elif draft.phase == "reviewing":
            instruction = ("The current configuration is unique. Use run_simulation to run it, "
                           "or select_parameter to change an unused setting.")
        elif draft.selections:
            instruction = ("The current configuration already exists in the simulation database. "
                           "Choose which setting to change using select_parameter; this draft cannot run yet.")
        else:
            instruction = ("The draft starts with baseline values from the golden configuration. "
                           "Use select_parameter to choose a setting to change.")
        expiry = ("then Ax3l submits the saved unique configuration and continues the normal experiment cycle. "
                  if draft.selections else
                  "then Ax3l restarts from the initial prompt in a fresh conversation, discarding the tentative "
                  "parameter selection and all previous messages. ")
        super().__init__(
            instruction + f" Aim to decide within {PARAMETER_SELECTION_SECONDS // 60} minutes. "
            "After each data_tool request you will receive the remaining time. "
            "The same timer applies while choosing values. An accepted unique change starts a fresh "
            "five-minute budget. "
            f"An expired budget gives you {DECISION_GRACE_SECONDS // 60} extra minutes; {expiry}"
            "Choose a key below. Each setting can change only once per experiment, and keeping the current "
            "values is not allowed. Paired values are submitted together. "
            "Use data_tool at / for measured reference runs or /draft for the current values.\n\n"
            f"Available parameter keys and current values:\n```json\n{json.dumps(choices, allow_nan=False)}\n```"
        )
