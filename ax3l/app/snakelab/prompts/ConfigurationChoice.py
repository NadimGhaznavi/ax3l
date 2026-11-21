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
    "loss": ("Faint lines show raw loss; bold lines show trailing means. "
             "Gaps mean loss was unrecorded. Look for sustained rises and repeated spikes.",
             ("episodes_with_loss",), "activity", "move and loss counts"),
    "scores": ("Use the score trend to consider how quickly to reduce random moves.",
               ("mean_first_50_scores", "mean_last_50_scores", "epsilon_random_actions"), "scores", "score statistics"),
    "distribution": ("Use the spread of scores to judge how reliably the snake found food.",
                     ("median_score", "zero_score_episodes", "high_score_episodes"), "endings", "how episodes ended"),
}


class ConfigurationChoice(Prompt):
    def __init__(self, draft: ConfigurationDraft, latest: SimulationAnalysis,
                 golden: SimulationAnalysis, chart_scope: str, png: bytes | None):
        parameter = draft.next_parameter
        tool = ("request_seed_change" if parameter == "seed" else
                "submit_pair_values" if parameter in PAIR_PARAMETERS else "submit_single_value")
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
        text = [f"Choose {CHOICE_LABELS[parameter]}.", KnowledgeBase().read("/selection")]
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
                text.append("This reference uses a different seed from the draft. "
                            "Its measurements and chart are historical context for this choice.")
            text.append(f"See {label} at /{chart_scope}/{page} in data_tool.")
        text.append("Use data_tool at /draft for saved choices or / for other runs.")
        if parameter == "seed":
            text.append(f"Call {tool} with no arguments to save a seed change. "
                        "Ax3l picks the next seed that avoids stored drafts and golden baselines. "
                        "When you run the draft, Ax3l first reruns golden on the new seed. "
                        "That score becomes the local baseline, even if lower. "
                        "If you saved other changes, Ax3l then runs them against that baseline.")
        else:
            text.append(f"Use {tool} to change at least one value. "
                        "If the full configuration already exists, try different values for this setting.")
        text.append(f"Measured data and current values:\n```json\n{json.dumps(evidence, allow_nan=False)}\n```")
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
