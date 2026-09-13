"""Request a value for the assigned parameter."""

from ax3l.app.Prompt import Prompt


class FirstContactPair(Prompt):
    def __init__(self, parameter):
        super().__init__(
            f"Choose an untested {parameter} value to improve the current golden high score. "
            'Call submit_pair_values with {"value_1": number_1, "value_2": number_2}.'
        )
