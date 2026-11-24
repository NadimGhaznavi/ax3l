"""Prepare a view's settings without changing the underlying configuration."""

from copy import deepcopy

from ax3l.entities.ExperimentView import ExperimentView
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


def view_values(view: ExperimentView, config: dict) -> dict:
    return {name: SimulationConfiguration.value_at(config, tuple(name.split(".")))
            for name in view.parameters}


def apply_values(config: dict, values: dict[str, int | float]) -> dict:
    result = deepcopy(config)
    for name, value in values.items():
        path = name.split(".")
        node = result
        for part in path[:-1]:
            node = node[part]
        node[path[-1]] = value
    return result


def other_parameters(view: ExperimentView, config: dict, proposed: set[str]) -> dict:
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

    return remaining(config)


def editable_parameters(view: ExperimentView, config: dict) -> dict:
    return {
        name: {
            "value": SimulationConfiguration.value_at(config, tuple(name.split("."))),
            "rules": {key: value for key, value in
                      SimulationConfiguration.field(tuple(name.split("."))).items()
                      if key not in ("default", "title", "x-snakelab-unit")},
        } for name in view.parameters
    }
