"""Request an initial proposal for the distance reward pair."""

from ax3l.app.Prompt import Prompt
from ax3l.interface.SimulationConfiguration import SCHEMA


class FirstContactRewardPair(Prompt):
    def __init__(self):
        fields = SCHEMA["properties"]["game"]["properties"]["rewards"]["properties"]
        super().__init__(
            f"closer_to_food: {fields['closer_to_food']['description']}\n"
            f"further_from_food: {fields['further_from_food']['description']}\n\n"
            "Tune closer_to_food and further_from_food together. "
            "Their balance determines how strongly the agent is rewarded for moving "
            "toward food versus penalized for moving away. This matters because some "
            "safe paths require temporary detours. "
            "Use the tool's enumerated integer or fractional values. The sum of the "
            "two values must be <= 0 to avoid rewarding loops without food. "
            "Food gives +10, collisions and move-limit endings give -10, and empty "
            "moves have zero base reward. Consider the zero-shaping control (0, 0). "
            "Choose an untested pair that you believe can improve the current golden "
            "high score while keeping all other configuration values fixed. "
            "Either value may remain unchanged, but the pair as a whole must be new. "
            'Call submit_pair_values with {"value_1": number, "value_2": number}, '
            "where value_1 is closer_to_food and value_2 is further_from_food."
        )
