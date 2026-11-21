"""Request an initial proposal for the distance reward pair."""

from ax3l.app.Prompt import Prompt
from ax3l.interface.SimulationConfiguration import SCHEMA


class FirstContactRewardPair(Prompt):
    def __init__(self):
        fields = SCHEMA["properties"]["game"]["properties"]["rewards"]["properties"]
        super().__init__(
            f"closer_to_food: {fields['closer_to_food']['description']}\n"
            f"further_from_food: {fields['further_from_food']['description']}\n\n"
            "Choose an untested pair to beat golden's high score. Use the tool's allowed values; "
            "their sum must be <= 0. Consider (0, 0). Change at least one value and "
            "keep other rewards at their draft values. "
            'Call submit_pair_values with {"value_1": number, "value_2": number}, '
            "where value_1 is closer_to_food and value_2 is further_from_food."
        )
