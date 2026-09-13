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
            "Submit exactly one submit_single_value tool call with parameter set to the exact "
            "JSON spec key and value set to your chosen JSON number. Prose suggestions or a "
            "configuration JSON block do not submit a simulation."
        )
