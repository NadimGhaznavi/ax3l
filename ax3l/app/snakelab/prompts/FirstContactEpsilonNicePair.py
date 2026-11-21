"""Request a joint safe-exploration proposal."""

from ax3l.app.Prompt import Prompt
from ax3l.app.snakelab.PairParameters import pair_instructions


class FirstContactEpsilonNicePair(Prompt):
    def __init__(self):
        super().__init__(
            pair_instructions("epsilon_nice_pair") + "\n\n"
            "Tune EpsilonNice probability and steps together. Probability is the chance "
            "per eligible non-detour move of scheduling a detour starting next move. "
            "Steps is its duration; detours reset each episode. Each detour move chooses "
            "an immediately safe alternative to the model suggestion if one exists. "
            "EpsilonNice is required and its probability must remain positive. It only "
            "activates after ordinary epsilon expires; slow decay can leave it inactive "
            "throughout a 750-episode run. Choose an untested pair while keeping all "
            "other settings fixed. Either value may remain unchanged. "
            'Call submit_pair_values with {"value_1": number, "value_2": integer}.'
        )
