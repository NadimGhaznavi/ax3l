"""Request a value for the assigned parameter."""

from ax3l.app.Prompt import Prompt


class ComparisonSingle(Prompt):
    def __init__(self, parameter):
        super().__init__(
            f"Choose an untested {parameter} value to improve the current golden high score. "
            'Call submit_single_value with {"value": number}.'
        )
