"""Give Qwen one chart, one question, and an example of a bounded answer."""

import base64
import json

from ax3l.app.Prompt import Prompt
from ax3l.constants.DSimulationAnalysis import DSimulationAnalysis


class AnalyzeSimulation(Prompt):
    def __init__(self, config: dict, metrics: dict, png: bytes, section: str):
        question, fields, example = {
            "scores": (
                "Compare the supplied mean scores for the first 50 and final 50 episodes of this same run. "
                "Is the final mean higher, lower, or equal?",
                {"mean_first_50_scores": "first 50 mean", "mean_last_50_scores": "last 50 mean"},
                "The first 50 episodes averaged 0.2 points and the final 50 averaged 0.1 points, "
                "so the final average was lower."),
            "distribution": (
                "Describe whether high scores are common or rare within this run.",
                {"high_score": "high score", "mean_score": "mean score", "median_score": "median score",
                 "zero_score_episodes": "zero scores", "high_score_episodes": "high-score episodes"},
                "Most episodes scored zero; only 16 of 500 reached the one-point high score."),
            "loss": (
                "Describe the training loss trend and any spikes or missing measurements.",
                {"episodes_with_loss": "episodes with loss"},
                "Recorded loss declined early and then stayed mostly flat with occasional spikes. "
                "This alone does not show that scores improved."),
        }[section]
        facts = "; ".join(f"{label}: {'unrecorded' if metrics[name] is None else metrics[name]}"
                          for name, label in {"episodes": "episodes", **fields}.items())
        super().__init__(
            f"Task: {DSimulationAnalysis.SECTIONS[section]} for this run, "
            f"seed {config['seed']}.\n{question}\n"
            f"Facts: {facts}\n"
            "Call submit_simulation_summary: 1–2 sentences, at most 40 words, then stop. "
            "Use facts for numbers. This chart only; no settings or causal claims.\n"
            f"Example format (invented data): {example}\n"
            f"Guide: kb_tool /analysis/{section}."
        )
        self._image_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")

    def to_json(self) -> str:
        return json.dumps({"role": "user", "content": [
            {"type": "text", "text": self.to_md()},
            {"type": "image_url", "image_url": {"url": self._image_url}},
        ]}, ensure_ascii=False)
