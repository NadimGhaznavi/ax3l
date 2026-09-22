"""Aggregate consecutive completed simulations and plot bucket mean runtimes and steps."""

from statistics import mean, median

import plotly.graph_objects as go

from ax3l.constants.DReportMgr import DReportMgr


def buckets(history: list[dict], bucket_size: int) -> list[dict]:
    """Assign every run to one bucket, retaining the final partial bucket."""
    result = []
    for offset in range(0, len(history), bucket_size):
        runs = history[offset:offset + bucket_size]
        bucket = dict(number=len(result) + 1, first=offset + 1,
                      last=offset + len(runs), count=len(runs))
        for field in ("runtime_seconds", "llm_seconds", "high_score", "total_steps", "steps_per_episode"):
            values = [float(run[field]) for run in runs if run[field] is not None]
            bucket[field] = mean(values) if values else None
            bucket[field + "_count"] = len(values)
            if field == "high_score":
                bucket["median_high_score"] = median(values) if values else None
        result.append(bucket)
    return result


def metrics(history: list[dict], bucket_size: int = DReportMgr.SIMULATION_BUCKET_SIZE) -> dict:
    summaries = buckets(history, bucket_size)
    result = dict(chart=None, steps_chart=None, total=len(history), bucket_size=bucket_size, bucket_count=len(summaries))
    if not summaries:
        return result

    def detail(bucket: dict, field: str, count_field: str) -> str:
        value = bucket[field]
        return "Unavailable" if value is None else f"{value:,.2f} ({bucket[count_field]} runs)"

    details = [[
        bucket["first"], bucket["last"], bucket["count"],
        detail(bucket, "high_score", "high_score_count"),
        detail(bucket, "median_high_score", "high_score_count"),
        detail(bucket, "total_steps", "total_steps_count"),
        detail(bucket, "steps_per_episode", "steps_per_episode_count"),
        bucket["runtime_seconds_count"], bucket["llm_seconds_count"],
    ] for bucket in summaries]
    figure = go.Figure()
    for field, name, color, count_index in (
        ("runtime_seconds", "Simulation Runtime", "#4c9be8", 7),
        ("llm_seconds", "LLM Time", "#f09445", 8),
    ):
        figure.add_trace(go.Scatter(
            x=[bucket["number"] for bucket in summaries],
            y=[bucket[field] / 60 if bucket[field] is not None else None for bucket in summaries], customdata=details,
            mode="lines+markers", name=name, connectgaps=False,
            line=dict(shape="spline", color=color, width=4), marker=dict(size=6),
            hovertemplate="Bucket: %{x}<br>Simulations: %{customdata[0]}–%{customdata[1]}"
                          " (%{customdata[2]} runs)<br>Mean time: %{y:.3f} min"
                          f" (%{{customdata[{count_index}]}} runs)"
                          "<br>Mean high score: %{customdata[3]}<br>Median high score: %{customdata[4]}"
                          "<br>Mean total steps: %{customdata[5]}<br>Mean steps per episode: %{customdata[6]}"
                          "<extra>%{fullData.name}</extra>",
        ))
    steps_figure = go.Figure(go.Scatter(
        x=[bucket["number"] for bucket in summaries],
        y=[bucket["total_steps"] for bucket in summaries],
        customdata=[[bucket["first"], bucket["last"], bucket["count"],
                     bucket["total_steps_count"]] for bucket in summaries],
        mode="lines+markers", name="Steps per Simulation", connectgaps=False,
        line=dict(shape="spline", color="#4c9be8", width=4), marker=dict(size=6),
        hovertemplate="Bucket: %{x}<br>Simulations: %{customdata[0]}–%{customdata[1]}"
                      " (%{customdata[2]} runs)<br>Mean total steps: %{y:,.2f}"
                      " (%{customdata[3]} runs)<extra>%{fullData.name}</extra>",
    ))
    for plot, key, div_id, y_title in (
        (figure, "chart", "simulation-runtime", "Mean time (minutes)"),
        (steps_figure, "steps_chart", "steps-per-simulation", "Mean steps per simulation"),
    ):
        plot.update_layout(
            template="plotly_dark", paper_bgcolor="#101720", plot_bgcolor="#151f2b",
            font=dict(family="Courier New, monospace", color="#d5dfeb"),
            xaxis_title=f"Simulation bucket ({bucket_size} runs per bucket)", yaxis_title=y_title,
            xaxis=dict(rangemode="tozero", dtick=1 if len(summaries) < 20 else None),
            yaxis=dict(rangemode="tozero"),
            showlegend=True,
            legend=dict(orientation="h", x=.5, xanchor="center", y=-.22, yanchor="top"),
            margin=dict(l=65, r=25, t=30, b=115),
        )
        result[key] = plot.to_html(
            full_html=False, include_plotlyjs=key == "chart", div_id=div_id, default_height="65vh",
            config={"responsive": True, "displaylogo": False},
        )
    return result
