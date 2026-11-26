"""Prepare a view's settings without changing the underlying configuration."""

from copy import deepcopy

from ax3l.constants.DViewConversation import DViewConversation
from ax3l.entities.ExperimentView import ExperimentView
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


def parameter_schema(name: str) -> dict:
    if name == DViewConversation.NEW_SEED:
        return dict(type="boolean", description="Request a new random seed for this experiment.")
    return SimulationConfiguration.field(tuple(name.split(".")))


def view_values(view: ExperimentView, config: dict) -> dict:
    return {name: False if name == DViewConversation.NEW_SEED else
            SimulationConfiguration.value_at(config, tuple(name.split(".")))
            for name in view.parameters}


def apply_values(config: dict, values: dict[str, int | float | bool]) -> dict:
    result = deepcopy(config)
    for name, value in values.items():
        if name == DViewConversation.NEW_SEED:
            continue
        path = name.split(".")
        node = result
        for part in path[:-1]:
            node = node[part]
        node[path[-1]] = value
    return result


def other_parameters(view: ExperimentView, config: dict, proposed: set[str], *, new_seed: bool = False) -> dict:
    def remaining(node, prefix=""):
        result = {}
        for key, value in node.items():
            name = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                children = remaining(value, name)
                if children:
                    result[key] = children
            elif name not in view.parameters:
                result[key] = f"{value} (draft)" if name in proposed else value
        return result

    result = remaining(config)
    if DViewConversation.NEW_SEED not in view.parameters:
        result[DViewConversation.NEW_SEED] = new_seed
    return result


def editable_parameters(view: ExperimentView, config: dict) -> dict:
    return {
        name: {
            "value": current,
            "rules": {key: value for key, value in
                      parameter_schema(name).items()
                      if key not in ("default", "title", "x-snakelab-unit")},
        } for name, current in view_values(view, config).items()
    }
