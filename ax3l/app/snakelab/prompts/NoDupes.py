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
            f"The proposed {CHOICE_LABELS[parameter]} values {values} produce a configuration that already exists. "
            "The proposal was not saved. Keep working on this selected setting; do not choose another parameter. "
            f"Submit different values using {tool} until the complete configuration is unique. "
            "Other draft values stay unchanged. Use data_tool to research values if needed."
        )
