"""Related simulation parameter paths for comparison queries."""


PAIR_PARAMETERS = {
    "epsilon_pair": (("epsilon", "initial"), ("epsilon", "decay")),
    "reward_pair": (("game", "rewards", "closer_to_food"),
                    ("game", "rewards", "further_from_food")),
    "epsilon_nice_pair": (("epsilon_nice", "probability"), ("epsilon_nice", "steps")),
}
