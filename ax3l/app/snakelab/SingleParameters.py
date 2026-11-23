"""Schema-backed paths for tunable single parameters."""
from ax3l.interface.SimulationConfiguration import SCHEMA

EXCLUDED = {"seed", "closer_to_food", "further_from_food", "initial", "decay", "probability", "steps"}


def _fields(node, path=()):
    for name, field in node["properties"].items():
        if field["type"] == "object":
            yield from _fields(field, path + (name,))
        elif name not in EXCLUDED and "const" not in field:
            yield name, (path + (name,), field)


SINGLE_PARAMETERS = dict(_fields(SCHEMA))
