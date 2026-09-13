"""Introduce the available single-parameter search space."""

from ax3l.app.Prompt import Prompt
from ax3l.app.snakelab.SingleParameters import parameter_instructions


class FirstContactSingle(Prompt):
    def __init__(self, parameter=None):
        super().__init__(
            "The baseline is the current Golden Configuration. Choose exactly one parameter "
            "from the list below and one new value different from its current golden value. "
            "Keep every other configuration setting unchanged.\n"
            + parameter_instructions(parameter) + "\n"
            "Call submit_single_value with the chosen parameter's exact JSON spec key and value."
        )
