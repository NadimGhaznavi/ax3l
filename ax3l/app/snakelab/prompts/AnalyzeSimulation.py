"""Ask for one bounded, reusable interpretation of a completed run."""

import base64
import json

from ax3l.app.Prompt import Prompt


class AnalyzeSimulation(Prompt):
    def __init__(self, run_id: str, config: dict, metrics: dict, png: bytes):
        super().__init__(
            f"Analyze completed simulation {run_id.split('-')[0]}, seed {config['seed']}. "
            "The project goal is to improve the simulation high score over 500 episodes. "
            "Exact measured results follow; use these numbers rather than estimating from pixels.\n"
            f"{json.dumps(metrics, allow_nan=False)}\n"
            f"Configuration:\n{json.dumps(config, allow_nan=False)}\n"
            "Submit 2–3 sentences, at most 80 words, with submit_simulation_summary. "
            "Describe score trends, consistency, loss/exploration patterns, and relevant termination reasons. "
            "Loss is diagnostic; lower loss alone does not demonstrate better scores, and reward changes "
            "can change its scale. Distinguish observations from possible explanations; do not attribute "
            "causation to individual settings. Keep observations intrinsic to this run: do not refer to "
            "its current latest/golden/all-time role or compare it with a changing target. "
            "Ax3l supplies those comparisons separately. Missing loss values are unrecorded, not zero."
        )
        self._image_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")

    def to_json(self) -> str:
        return json.dumps({"role": "user", "content": [
            {"type": "text", "text": self.to_md()},
            {"type": "image_url", "image_url": {"url": self._image_url}},
        ]}, ensure_ascii=False)
