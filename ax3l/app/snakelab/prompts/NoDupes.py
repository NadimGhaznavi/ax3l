"""Keep Qwen on its selected setting until it produces a unique configuration."""

import json

from ax3l.app.Prompt import Prompt
from ax3l.app.snakelab.PairParameters import PAIR_PARAMETERS
from ax3l.app.snakelab.ParameterSpace import parameter_values
from ax3l.constants.DChoice import CHOICE_LABELS


class NoDupes(Prompt):
    def __init__(self, parameter: str, candidate: dict):
        tool = "submit_pair_values" if parameter in PAIR_PARAMETERS else "submit_single_value"
        values = json.dumps(parameter_values(candidate, parameter), allow_nan=False)
        super().__init__(
            f"Duplicate draft with {CHOICE_LABELS[parameter]} values {values}. "
            f"Use {tool} with different values for this same setting."
        )
