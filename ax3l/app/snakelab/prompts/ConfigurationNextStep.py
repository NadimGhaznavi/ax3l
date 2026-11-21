"""Ask Qwen which parameter to change or whether to run a unique draft."""

import json

from ax3l.app.Prompt import Prompt
from ax3l.app.snakelab.ParameterSpace import parameter_values
from ax3l.constants.DChoice import CHOICE_LABELS
from ax3l.entities.ConfigurationDraft import ConfigurationDraft


class ConfigurationNextStep(Prompt):
    def __init__(self, draft: ConfigurationDraft, parameters: list[str]):
        choices = {parameter: dict(label=CHOICE_LABELS[parameter], values=parameter_values(draft.config, parameter))
                   for parameter in parameters}
        if draft.phase == "reviewing" and not choices:
            instruction = "Call run_simulation. The draft is unique and no untested changes remain."
        elif draft.phase == "reviewing":
            instruction = "Call run_simulation for this unique draft, or select_parameter with a listed key."
        elif draft.selections:
            instruction = "This draft already exists. Call select_parameter with a listed key to make it unique."
        else:
            instruction = "The draft starts from golden. Use the run data to choose a listed key with select_parameter."
        text = [instruction, "Aim to beat golden's high score in 500 episodes. Prefer same-seed evidence."]
        if choices:
            text.append("Choose any subset in any order, at most once per setting. Change at least one value and "
                        "submit pairs together. Revise duplicates within the same setting.")
            text.append("The timer continues during value selection. A saved unique change resets it.")
        if "seed" in choices:
            text.append("Select seed to let Ax3l choose the next unused seed. On run, golden sets the new seed's "
                        "baseline even if it scores lower. Other changes run afterward against that baseline.")
        elif "seed" in draft.selections:
            text.append("The seed can change only once per draft and is already set.")
        text.append("Use data_tool at / for reference runs or /draft for current values.")
        text.append(f"Available keys and current values\n```json\n{json.dumps(choices, allow_nan=False)}\n```")
        super().__init__("\n\n".join(text))
