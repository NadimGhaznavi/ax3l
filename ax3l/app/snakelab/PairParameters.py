"""Schema-backed assignments for joint parameter proposals."""

from ax3l.activity.ParameterRules import parameter_rules
from ax3l.constants.DChoice import CHOICE_LABELS, PAIR_LABELS
from ax3l.interface.SimulationConfiguration import SCHEMA


PAIR_PARAMETERS = {
    "epsilon_pair": (("epsilon", "initial"), ("epsilon", "decay")),
    "reward_pair": (("game", "rewards", "closer_to_food"),
                    ("game", "rewards", "further_from_food")),
    "epsilon_nice_pair": (("epsilon_nice", "probability"), ("epsilon_nice", "steps")),
}


def pair_instructions(pair: str) -> str:
    lines = [f"Choose {CHOICE_LABELS[pair]}."]
    if pair == "reward_pair":
        lines.append("Closer reward + farther reward must be at most zero, to avoid rewarding loops.")
    for index, path in enumerate(PAIR_PARAMETERS[pair], start=1):
        field = SCHEMA
        for key in path:
            field = field["properties"][key]
        label = PAIR_LABELS[pair][index - 1]
        lines.append(f"value_{index} = {label}: {parameter_rules(field)}")
    return "\n".join(lines)
