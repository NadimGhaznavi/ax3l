"""Ask for a fresh learning-rate proposal after comparing completed runs."""

import json
from pathlib import Path

from ax3l.app.Prompt import Prompt


class ComparisonSingle(Prompt):
    def __init__(self):
        schema = json.loads((Path(__file__).parent.parent / "simulation-config-v2.schema.json").read_text())
        field = schema["properties"]["training"]["properties"]["learning_rate"]
        super().__init__(
            f"Learning Rate: {field['description']}\n"
            f"Choose a JSON number from {field['minimum']} through {field['maximum']}, inclusive. "
            "Change only learning_rate in the current golden configuration. "
            "The resulting complete configuration must differ from the golden configuration "
            "and every previously submitted configuration. Use the comparison history and loss curves "
            "to choose a promising unexplored value, even if the latest simulation did not improve the score. "
            "Call submit_single_value with parameter=learning_rate and your chosen value."
        )
