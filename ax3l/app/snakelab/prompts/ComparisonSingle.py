"""Ask for a fresh single-parameter proposal after comparing completed runs."""

from ax3l.app.Prompt import Prompt
from ax3l.app.snakelab.SingleParameters import parameter_instructions


class ComparisonSingle(Prompt):
    def __init__(self):
        super().__init__(
            "Choose exactly one parameter from the list below and change only its value in the "
            "current golden configuration. Keep every other setting unchanged.\n"
            + parameter_instructions() + "\n"
            "The resulting complete configuration must differ from the golden configuration "
            "and every previously submitted configuration. Use the comparison history "
            "to choose a promising unexplored value, even if the latest simulation did not improve the score. "
            "Call submit_single_value with the chosen parameter's exact JSON spec key and value."
        )
