"""Interactive score histogram with a shared bin definition for both cohorts."""

import math

import plotly.graph_objects as go


def distribution(scores: list[int | None]) -> dict:
    half = len(scores) // 2
    all_scores = [score for score in scores if score is not None]
    older_scores = [score for score in scores[:half] if score is not None]
    figure = go.Figure()
    if all_scores:
        low, high = min(all_scores), max(all_scores)
        size = max(1, math.ceil((high - low + 1) / 40))
        bins = dict(start=low - .5, end=high + .5, size=size)
        for name, values, color in (
            ("All runs", all_scores, "#80ff98"),
            ("Oldest half", older_scores, "#ffad55"),
        ):
            figure.add_trace(go.Histogram(
                x=values, name=name, xbins=bins, bingroup="scores",
                histfunc="count", marker_color=color, opacity=.85,
                hovertemplate="Score: %{x}<br>Runs: %{y}<extra>%{fullData.name}</extra>",
            ))
        figure.update_layout(
            barmode="overlay", bargap=.08, template="plotly_dark",
            paper_bgcolor="#050a06", plot_bgcolor="#0a140d",
            font=dict(family="Courier New, monospace", color="#80ff98"),
            xaxis_title="Run high score", yaxis_title="Number of runs",
            yaxis=dict(rangemode="tozero", dtick=1 if len(all_scores) < 20 else None),
            legend=dict(orientation="h", y=1.15),
            margin=dict(l=65, r=25, t=85, b=65),
        )
    return dict(
        total=len(scores), half=half, scored=len(all_scores), older_scored=len(older_scores),
        chart=figure.to_html(full_html=False, include_plotlyjs=True,
                             div_id="score-histogram", default_height="65vh",
                             config={"responsive": True, "displaylogo": False}) if all_scores else None,
    )
