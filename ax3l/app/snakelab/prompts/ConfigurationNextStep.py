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
                           "Research which setting would be best to tweak, then choose it using select_parameter.")
        expiry = ("then Ax3l submits the saved unique configuration and continues the normal experiment cycle. "
                  if draft.selections else
                  "then Ax3l restarts from the initial prompt in a fresh conversation, discarding the tentative "
                  "parameter selection and all previous messages. ")
        seed_instruction = ("The seed has already been changed for this draft and cannot be changed again. "
                            if "seed" in draft.selections else
                            "Select seed to request a seed change once per draft: Ax3l increments it and skips "
                            "configurations already stored. You do not choose the seed's numeric value. ")
        super().__init__(
            instruction + f" Aim to make this decision within {PARAMETER_SELECTION_SECONDS // 60} minutes. "
            "After each data_tool request you will receive the remaining time. "
            "The countdown continues while choosing a value. An accepted unique change starts a fresh five-minute "
            "budget to choose another parameter or run the configuration. "
            f"An expired budget gives you {DECISION_GRACE_SECONDS // 60} extra minutes; {expiry}"
            "Paired settings are changed together. Other values stay in the draft. "
            f"{seed_instruction}When the draft runs, Ax3l first runs golden with the new "
            "seed and accepts its score as the local golden baseline, even if lower. If other settings changed, "
            "Ax3l then runs the complete draft on that seed and compares it with the new baseline. "
            "Each setting may be selected only once per experiment. Once selected, you must change at least one "
            "of its values; keeping the current values is not allowed. "
            "Choose only from the available parameter keys below. Settings with no untested changes for the "
            "current seed and other draft settings are omitted. "
            "After each submitted change, Ax3l checks the complete configuration for uniqueness. "
            "Duplicate values must be revised within the selected setting before you can choose another setting. "
            "You choose which settings to adjust and when to run; there is no required parameter order. "
            "Use data_tool at / for measured reference runs or /draft for the current values.\n\n"
            f"Available parameter keys and current values:\n```json\n{json.dumps(choices, allow_nan=False)}\n```"
        )
