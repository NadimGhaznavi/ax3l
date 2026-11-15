"""Schema-backed search space for single-parameter proposals."""

from ax3l.activity.ParameterRules import parameter_rules
from ax3l.constants.DChoice import CHOICE_LABELS
from ax3l.interface.SimulationConfiguration import SCHEMA

EXCLUDED = {"seed", "closer_to_food", "further_from_food", "initial", "decay", "probability", "steps"}


def _fields(node, path=()):
    for name, field in node["properties"].items():
        if field["type"] == "object":
            yield from _fields(field, path + (name,))
        elif name not in EXCLUDED and "const" not in field:
            yield name, (path + (name,), field)


SINGLE_PARAMETERS = dict(_fields(SCHEMA))


def parameter_instructions(parameter=None):
    names = list(SINGLE_PARAMETERS) if parameter is None else [parameter]
    lines = []
    for name in names:
        _, field = SINGLE_PARAMETERS[name]
        lines.append(f"{CHOICE_LABELS[name]}: {parameter_rules(field)}")
    return "\n".join(lines)
