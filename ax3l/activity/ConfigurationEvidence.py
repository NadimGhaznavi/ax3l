"""Prepare measured choice evidence without formatting conversation text."""

from ax3l.app.snakelab.ParameterSpace import parameter_values
from ax3l.constants.DChoice import CHOICE_CHARTS
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
from ax3l.entities.SimulationAnalysis import SimulationAnalysis


CHART_EVIDENCE = {
    "loss": (("episodes_with_loss",), "activity"),
    "scores": (("mean_first_50_scores", "mean_last_50_scores", "epsilon_random_actions"), "scores"),
    "distribution": (("median_score", "zero_score_episodes", "high_score_episodes"), "endings"),
    "endings": (("termination_reasons",), "endings"),
}


def choice_context(draft: ConfigurationDraft, latest: SimulationAnalysis,
                   golden: SimulationAnalysis, chart_scope: str, has_image: bool) -> dict:
    parameter, seed = draft.next_parameter, draft.config["seed"]
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
    context = dict(evidence=evidence, chart=chart, chart_scope=chart_scope, has_image=has_image)
    if chart is not None:
        fields, page = CHART_EVIDENCE[chart]
        evidence["reference_runs"][chart_scope].update(
            {field: references[chart_scope].metrics[field] for field in ("episodes", *fields)})
        if has_image and chart == "loss" and chart_scope != "golden":
            evidence["reference_runs"]["golden"].update(
                {field: golden.metrics[field] for field in ("episodes", *fields)})
        context.update(data_page=page, golden_has_loss=bool(golden.metrics["episodes_with_loss"]),
                       same_seed=references[chart_scope].config["seed"] == seed)
    return context
