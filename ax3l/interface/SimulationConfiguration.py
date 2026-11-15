"""Own Ax3l's simulation defaults, field validation, and experiment policy."""

import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError


SCHEMA = json.loads((Path(__file__).parents[1] / "app/snakelab/simulation-config-v2.schema.json").read_text())
_VALIDATOR = Draft202012Validator(SCHEMA)


class SimulationConfiguration:
    @staticmethod
    def field(path: tuple[str, ...]) -> dict:
        field = SCHEMA
        for key in path:
            field = field["properties"][key]
        return field

    @staticmethod
    def defaults() -> dict:
        def defaults(node):
            if node["type"] == "object":
                return {name: defaults(child) for name, child in node["properties"].items()}
            return node["default"]

        config = defaults(SCHEMA)
        SimulationConfiguration.validate(config)
        return config

    @staticmethod
    def value(path: tuple[str, ...], value: int | float) -> int | float:
        if type(value) not in (int, float) or (isinstance(value, float) and not math.isfinite(value)):
            raise ValidationError("must be a finite JSON number", path=path)
        field = SimulationConfiguration.field(path)
        Draft202012Validator(field).validate(value)
        return int(value) if field["type"] == "integer" else value

    @staticmethod
    def reward_pair_allowed(closer: int | float, further: int | float) -> bool:
        return closer + further <= 0

    @staticmethod
    def validate_reward_pair(closer: int | float, further: int | float) -> None:
        if not SimulationConfiguration.reward_pair_allowed(closer, further):
            raise ValidationError(
                "closer_to_food + further_from_food must be <= 0 to avoid rewarding loops",
                path=("game", "rewards"),
            )

    @staticmethod
    def validate(config: dict) -> None:
        _VALIDATOR.validate(config)
        rewards = config["game"]["rewards"]
        SimulationConfiguration.validate_reward_pair(rewards["closer_to_food"], rewards["further_from_food"])
