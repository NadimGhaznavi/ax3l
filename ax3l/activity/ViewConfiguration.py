"""Prepare a view's settings without changing the underlying configuration."""

from copy import deepcopy

from ax3l.entities.ExperimentView import ExperimentView
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


def parameter_schema(name: str) -> dict:
    return SimulationConfiguration.field(tuple(name.split(".")))


def view_values(view: ExperimentView, config: dict) -> dict:
    return {name: SimulationConfiguration.value_at(config, tuple(name.split(".")))
            for name in view.parameters}


def historical_values(view: ExperimentView, runs: list[dict]) -> dict[str, list[dict]]:
    """Group each run's view parameters by score, highest first, preserving ties."""
    history = {}
    for run in sorted(runs, key=lambda run: run["high_score"], reverse=True):
        history.setdefault(str(run["high_score"]), []).append(view_values(view, run["config"]))
    return history


def parameter_comparison(baseline: dict, values: dict[str, int | float | bool]) -> dict:
    return {
        name: {"baseline": SimulationConfiguration.value_at(baseline, tuple(name.split("."))),
               "latest": value}
        for name, value in values.items()
    }


def apply_values(config: dict, values: dict[str, int | float | bool]) -> dict:
    result = deepcopy(config)
    for name, value in values.items():
        path = name.split(".")
        node = result
        for part in path[:-1]:
            node = node[part]
        node[path[-1]] = value
    return result


def other_parameters(view: ExperimentView, config: dict) -> dict:
    def remaining(node, prefix=""):
        result = {}
        for key, value in node.items():
            name = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                children = remaining(value, name)
                if children:
                    result[key] = children
            elif name not in view.parameters:
                result[key] = value
        return result

    return remaining(config)


def editable_parameters(view: ExperimentView, config: dict) -> dict:
    return {
        name: {
            "value": current,
            "rules": {key: value for key, value in
                      parameter_schema(name).items()
                      if key not in ("default", "title", "x-snakelab-unit")},
        } for name, current in view_values(view, config).items()
    }
