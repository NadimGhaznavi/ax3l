"""Present one setting choice with the evidence needed to make it."""

import base64
import json

from ax3l.app.Prompt import Prompt
from ax3l.app.snakelab.PairParameters import PAIR_PARAMETERS
from ax3l.app.snakelab.ParameterSpace import parameter_values
from ax3l.constants.DChoice import CHOICE_CHARTS, CHOICE_LABELS
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
from ax3l.entities.SimulationAnalysis import SimulationAnalysis
from ax3l.interface.KnowledgeBase import KnowledgeBase


CHART_EVIDENCE = {
    "loss": ("Faint lines show raw loss and bold lines show trailing means. "
             "Gaps mark missing loss. Look for sustained rises or repeated spikes.",
             ("episodes_with_loss",), "activity", "move and loss counts"),
    "scores": ("Use score trends to judge how quickly to reduce random moves.",
               ("mean_first_50_scores", "mean_last_50_scores", "epsilon_random_actions"), "scores", "score statistics"),
    "distribution": ("Use score spread to judge how reliably the snake found food.",
                     ("median_score", "zero_score_episodes", "high_score_episodes"), "endings", "how episodes ended"),
}


class ConfigurationChoice(Prompt):
    def __init__(self, draft: ConfigurationDraft, latest: SimulationAnalysis,
                 golden: SimulationAnalysis, chart_scope: str, png: bytes | None):
        parameter = draft.next_parameter
        if parameter == "seed":
            text = ["Call request_seed_change with no arguments. Ax3l saves the next unused seed, skipping stored "
                    "drafts and golden baselines. The draft still needs a run decision.",
                    "When the draft runs, golden sets the new seed's baseline even if it scores lower. "
                    "A seed-only draft ends there. Any other changes run on the new seed and must beat that baseline."]
        else:
            tool = "submit_pair_values" if parameter in PAIR_PARAMETERS else "submit_single_value"
            text = [f"Change {CHOICE_LABELS[parameter]} with {tool}. Follow the tool's limits and change at least "
                    "one value. If the complete draft is a duplicate, try different values for this setting.",
                    KnowledgeBase().read("/selection")]
        seed = draft.config["seed"]
        references = {"golden": golden}
        if latest.run_id != golden.run_id:
            references["latest"] = latest
        evidence = {
            "seed": seed,
            "current": parameter_values(draft.config, parameter),
            "reference_runs": {
                scope: {"seed": run.config["seed"], "high_score": run.metrics["high_score"],
                        "same_seed_as_draft": run.config["seed"] == seed,
                        "settings": parameter_values(run.config, parameter)}
                for scope, run in references.items()
            },
        }
        chart = CHOICE_CHARTS.get(parameter)
        if chart is not None:
            focus, fields, page, label = CHART_EVIDENCE[chart]
            metrics = references[chart_scope].metrics
            evidence["reference_runs"][chart_scope].update(
                {field: metrics[field] for field in ("episodes", *fields)})
            if png is not None:
                text.append(f"The chart shows the {chart_scope} run. {focus}")
                if chart == "loss" and chart_scope != "golden":
                    evidence["reference_runs"]["golden"].update(
                        {field: golden.metrics[field] for field in ("episodes", *fields)})
                    text.append("Orange overlays the golden run's raw loss and trailing mean."
                                if golden.metrics["episodes_with_loss"] else
                                "The golden run has no recorded loss to overlay.")
            if references[chart_scope].config["seed"] != seed:
                text.append("This reference uses a different seed from the draft. Treat it as historical context.")
            text.append(f"Use data_tool at /{chart_scope}/{page} for {label}.")
        text.append("Use data_tool at /draft for saved choices or / for reference runs.")
        text.append(f"Measured data and current values\n```json\n{json.dumps(evidence, allow_nan=False)}\n```")
        super().__init__("\n\n".join(text))
        self._png = png

    def to_json(self) -> str:
        if self._png is None:
            return super().to_json()
        url = "data:image/png;base64," + base64.b64encode(self._png).decode("ascii")
        return json.dumps({"role": "user", "content": [
            {"type": "text", "text": self.to_md()},
            {"type": "image_url", "image_url": {"url": url}},
        ]}, ensure_ascii=False)
