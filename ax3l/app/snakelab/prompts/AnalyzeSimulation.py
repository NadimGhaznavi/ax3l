"""Give Qwen one chart, one question, and an example of a bounded answer."""

import base64
import json

from ax3l.app.Prompt import Prompt
from ax3l.constants.DSimulationAnalysis import DSimulationAnalysis


class AnalyzeSimulation(Prompt):
    def __init__(self, run_id: str, config: dict, metrics: dict, png: bytes, section: str):
        question, fields, example = {
            "scores": (
                "Describe whether episode scores improve, decline, or stay flat during this run.",
                ("high_score", "mean_score", "mean_last_50_scores"),
                "Scores stayed low throughout training, with occasional one-point spikes. "
                "The final 50 episodes averaged 0.1 points."),
            "distribution": (
                "Describe whether high scores are common or rare within this run.",
                ("high_score", "mean_score", "median_score", "zero_score_episodes", "high_score_episodes"),
                "Most episodes scored zero; only 16 of 500 reached the one-point high score."),
            "loss": (
                "Describe the training loss trend and any spikes or missing measurements.",
                ("episodes_with_loss",),
                "Recorded loss declined early and then stayed mostly flat with occasional spikes. "
                "This alone does not show that scores improved."),
        }[section]
        facts = {"episodes": metrics["episodes"], **{name: metrics[name] for name in fields}}
        super().__init__(
            f"Task: {DSimulationAnalysis.SECTIONS[section]} for simulation {run_id.split('-')[0]}, "
            f"seed {config['seed']}.\n{question}\n"
            f"Measured facts: {json.dumps(facts, allow_nan=False)}\n"
            "Call submit_simulation_summary with 1–2 sentences, at most 40 words, then stop. "
            "Describe only this chart; use measured facts for exact numbers. "
            "Do not recommend settings or claim what caused the pattern.\n"
            f"Example format (invented data; use this run's facts): {example}\n"
            f"If you need chart guidance, use kb_tool with url /analysis/{section}."
        )
        self._image_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")

    def to_json(self) -> str:
        return json.dumps({"role": "user", "content": [
            {"type": "text", "text": self.to_md()},
            {"type": "image_url", "image_url": {"url": self._image_url}},
        ]}, ensure_ascii=False)
