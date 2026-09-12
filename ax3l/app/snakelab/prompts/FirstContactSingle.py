"""Introduce a single parameter using the simulation JSON spec."""

import json
from pathlib import Path

from ax3l.app.Prompt import Prompt


class FirstContactSingle(Prompt):
    def __init__(self, parameter: str):
        schema = json.loads(
            (Path(__file__).parent.parent / "simulation-config-v2.schema.json").read_text(
                encoding="utf-8"
            )
        )

        def find_parameters(node):
            for name, definition in node["properties"].items():
                if definition["type"] == "object":
                    yield from find_parameters(definition)
                elif name == parameter:
                    yield definition

        matches = list(find_parameters(schema))
        if len(matches) != 1:
            raise ValueError(
                f"Expected one parameter named {parameter!r}; found {len(matches)}"
            )

        self._name = parameter.replace("_", " ").title()
        self._desc = matches[0]["description"]

        rules = {key: value for key, value in matches[0].items()
                 if key in ("type", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
                            "multipleOf", "const", "enum")}
        message = (
            f"{self._name}: {self._desc} - This is the first simulation "
            "so you only have the simulation results from the baseline "
            "which is the current Golden Configuration.\n\n"
            f"Choose exactly one new value for {parameter}, different from its current golden value. "
            f"Change only {parameter}; keep every other configuration setting unchanged.\n"
            f"The value must satisfy these JSON Schema rules: {json.dumps(rules)}\n"
            f"Submit your choice by making exactly one submit_single_value tool call with "
            f"parameter={json.dumps(parameter)} and value set to your chosen JSON number. "
            "The tool submits the next simulation. Your response must contain that tool call; "
            "prose suggestions or a configuration JSON block do not submit a simulation."
        )

        super().__init__(message)
