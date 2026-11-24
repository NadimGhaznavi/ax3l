"""Summarize only the measurements relevant to the current view."""

from statistics import mean

from ax3l.activity.RunAnalysis import measure
from ax3l.activity.ViewConfiguration import view_values
from ax3l.entities.ExperimentView import ExperimentView


def run_evidence(result: dict, episodes: list[dict]) -> dict:
    metrics = measure(episodes, result["high_score"])
    for name, rows in (("first_50", episodes[:50]), ("last_50", episodes[-50:])):
        losses = [row["loss"] for row in rows if row["loss"] is not None]
        metrics[f"mean_{name}_loss"] = mean(losses) if losses else None
    return dict(config=result["config"], metrics=metrics)


def view_comparison(view: ExperimentView, golden: dict, latest: dict) -> dict:
    common = ("episodes", "high_score", "mean_score", "mean_first_50_scores", "mean_last_50_scores")
    fields = common + {
        "reward-signals": ("termination_reasons", "zero_score_episodes", "total_steps"),
        "architecture": ("median_score", "episodes_with_loss", "mean_first_50_loss", "mean_last_50_loss"),
        "training": ("episodes_with_loss", "mean_first_50_loss", "mean_last_50_loss", "total_steps"),
        "exploration": ("epsilon_random_actions", "nice_overrides", "zero_score_episodes"),
    }[view.name]

    def values(run):
        return dict(seed=run["config"]["seed"], parameters=view_values(view, run["config"]),
                    measurements={name: run["metrics"][name] for name in fields})

    return dict(golden=values(golden), latest=values(latest),
                high_score_change=latest["metrics"]["high_score"] - golden["metrics"]["high_score"])
