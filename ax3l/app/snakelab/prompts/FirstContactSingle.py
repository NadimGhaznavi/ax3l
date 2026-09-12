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

        message = (
            f"{self._name}: {self._desc} - This is the first simulation "
            "so you only have the simulation results from the baseline "
            "which is the current Golden Configuration."
        )

        super().__init__(message)
