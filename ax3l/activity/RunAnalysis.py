"""Calculate exact episode statistics and render one analysis chart at a time."""

from collections import Counter
from statistics import mean, median

import plotly.graph_objects as go

from ax3l.activity.PlotTicks import axis_ticks


def measure(episodes: list[dict], high_score: int) -> dict:
    scores = [episode["score"] for episode in episodes]
    outcomes = Counter(episode["outcome"] for episode in episodes)
    count = len(episodes)
    endings = {
        name: {"count": outcomes[name], "percent": 100 * outcomes[name] / count}
        for name in ("wall", "snake", "max_moves", "board_filled")
    } if count else {name: {"count": 0, "percent": 0.0}
                     for name in ("wall", "snake", "max_moves", "board_filled")}
    unknown = count - sum(item["count"] for item in endings.values())
    endings["unrecorded_or_other"] = {"count": unknown, "percent": 100 * unknown / count if count else 0.0}
    return {
        "episodes": count, "high_score": high_score,
        "mean_score": mean(scores) if scores else None,
        "median_score": median(scores) if scores else None,
        "mean_first_50_scores": mean(scores[:50]) if scores else None,
        "mean_last_50_scores": mean(scores[-50:]) if scores else None,
        "zero_score_episodes": scores.count(0),
        "high_score_episodes": scores.count(high_score),
        "total_steps": sum(episode["steps"] for episode in episodes),
        "termination_reasons": endings,
        "epsilon_random_actions": sum(episode["epsilon_injections"] or 0 for episode in episodes),
        "nice_overrides": sum(episode["epsilon_nice_injections"] or 0 for episode in episodes),
        "episodes_with_loss": sum(episode["loss"] is not None for episode in episodes),
    }


def render_analysis(config: dict, episodes: list[dict], metrics: dict,
                    target_score: int, section: str) -> bytes:
    figure = go.Figure()
    numbers = [episode["episode"] for episode in episodes]
    scores = [episode["score"] for episode in episodes]
    if section == "scores":
        title = "Episode Scores During Training"
        x_label, y_label = "Episode number (episodes)", "Episode score (points)"
        figure.add_trace(go.Scatter(x=numbers, y=scores, mode="lines", name="Episode score",
                                   line=dict(color="#80b8e8", width=1)))
        figure.add_trace(go.Scatter(
            x=numbers, y=[mean(scores[max(0, index - 19):index + 1]) for index in range(len(scores))],
            name="Trailing mean (up to 20 episodes)", line=dict(color="#d46512", width=3)))
        figure.add_hline(y=target_score, line_dash="dash", line_color="#994455",
                        annotation_text=f"Target at analysis: {target_score} points")
        epsilon_ended = next((episode["episode"] for episode in episodes if episode["epsilon"] == 0), None)
        if epsilon_ended is not None:
            figure.add_vline(x=epsilon_ended, line_dash="dot", line_color="#228833",
                            annotation_text="Ordinary epsilon ended")
    elif section == "distribution":
        title = "Episode Score Distribution"
        x_label, y_label = "Episode score (points)", "Number of episodes (episodes)"
        counts = Counter(scores)
        figure.add_trace(go.Bar(x=sorted(counts), y=[counts[value] for value in sorted(counts)],
                                name="Episode count", marker_color="#4477aa", showlegend=False))
    elif section == "loss":
        title = "Training Loss During Training"
        x_label, y_label = "Episode number (episodes)", "Mean Smooth L1 loss (native loss units)"
        figure.add_trace(go.Scatter(x=numbers, y=[episode["loss"] for episode in episodes],
                                   name="Recorded loss", connectgaps=False,
                                   line=dict(color="#4477aa", width=2)))
        if not metrics["episodes_with_loss"]:
            figure.add_annotation(text="No training losses recorded", x=.5, y=.5,
                                  xref="x domain", yref="y domain", showarrow=False)
    else:
        raise ValueError(f"Unknown analysis section: {section}")
    figure.update_xaxes(title_text=x_label, **axis_ticks(figure.data[0].x))
    figure.update_yaxes(title_text=y_label, rangemode="tozero")
    if section != "loss":
        values = [value for trace in figure.data for value in trace.y]
        if section == "scores":
            values.append(target_score)
        figure.update_yaxes(**axis_ticks(values))
    figure.update_layout(
        title=dict(text=f"{title}<br>"
                   f"<sup>Goal: improve the simulation high score | Seed {config['seed']} | "
                   f"{metrics['episodes']} episodes | High score {metrics['high_score']} points</sup>"),
        template="plotly_white", width=1100, height=650, font=dict(size=17),
        margin=dict(l=110, r=65, t=145, b=70),
        legend=dict(orientation="h", y=1.10, x=0),
    )
    return figure.to_image(format="png", scale=1)
