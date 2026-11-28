"""Provide simulation defaults and JSON field rules for LLM prompts and tools."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator


SCHEMA = json.loads((Path(__file__).with_name("schemas") / "simulation-config-v2.schema.json").read_text())


class SimulationConfiguration:
    @staticmethod
    def value_at(config: dict, path: tuple[str, ...]):
        for key in path:
            config = config[key]
        return config

    @staticmethod
    def field(path: tuple[str, ...]) -> dict:
        field = SCHEMA
        for key in path:
            field = field["properties"][key]
        return field

    @staticmethod
    def validate_values(values: object, parameters: tuple[str, ...]) -> None:
        """Validate proposed values using the same field rules supplied to the LLM."""
        Draft202012Validator(dict(type="object", minProperties=1, additionalProperties=False, properties={
            name: SimulationConfiguration.field(tuple(name.split("."))) for name in parameters
        })).validate(values)

    @staticmethod
    def defaults() -> dict:
        def defaults(node):
            if node["type"] == "object":
                return {name: defaults(child) for name, child in node["properties"].items()}
            return node["default"]

        return defaults(SCHEMA)
