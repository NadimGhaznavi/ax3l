"""Give one choice and point Qwen to small pages of saved experiment data."""

from ax3l.app.Prompt import Prompt
from ax3l.app.snakelab.PairParameters import PAIR_PARAMETERS
from ax3l.constants.DChoice import CHOICE_LABELS
from ax3l.entities.ConfigurationDraft import ConfigurationDraft


class ConfigurationChoice(Prompt):
    def __init__(self, draft: ConfigurationDraft, target: int):
        parameter = draft.next_parameter
        tool = "submit_pair_values" if parameter in PAIR_PARAMETERS else "submit_single_value"
        super().__init__(
            f"Goal: beat golden's {target} points on seed {draft.config['seed']}.\n"
            f"Choose {CHOICE_LABELS[parameter]}.\n"
            "Use data_tool: read /draft for current choices, then / for reference runs. "
            "Follow relevant links for scores, notes, or settings.\n"
            f"Call {tool} to save your choice. Same values allowed. "
            "Ax3l runs once all choices are saved."
        )
