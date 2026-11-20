"""Plot golden scores and same-seed ties, preserving seed baseline decreases."""

from html import escape

import plotly.graph_objects as go

from ax3l.activity.PlotTicks import axis_ticks


def highscores(history: list[dict], total: int) -> dict:
    if not history:
        return {"chart": None, "total": total}
    accepted = [row for row in history if not row["matched"]]
    x = [row["simulations"] for row in accepted]
    y = [row["score"] for row in accepted]
    seed_changes = [
        index > 0 and row["seed"] is not None and accepted[index - 1]["seed"] is not None
        and row["seed"] != accepted[index - 1]["seed"]
        for index, row in enumerate(accepted)
    ]
    figure = go.Figure()
    # Continue the accepted score across unsuccessful and pending submissions.
    end = max(total, max(row["simulations"] for row in history))
    figure.add_trace(go.Scatter(
        x=x + ([end] if end > x[-1] else []),
        y=y + ([y[-1]] if end > x[-1] else []),
        mode="lines", line=dict(shape="spline", color="#4c9be8", width=4),
        name="High score", hoverinfo="skip", showlegend=True,
    ))
    for rows, name, color, label in (
        ([row for row, changed in zip(accepted, seed_changes) if not changed],
         "Accepted config", "#f09445", ""),
        ([row for row, changed in zip(accepted, seed_changes) if changed],
         "Seed change", "#c792ea", "<br>Seed change"),
        ([row for row in history if row["matched"]],
         "Matched high score", "#64c9a0", "<br>Matched high score"),
    ):
        details = [
            [row["seed"], escape(row["run_id"].split('-')[0]), escape(row["reason"]), label]
            for row in rows
        ]
        figure.add_trace(go.Scatter(
            # A null point keeps the legend entry visible when this category is absent.
            x=[row["simulations"] for row in rows] or [None],
            y=[row["score"] for row in rows] or [None],
            customdata=details, mode="markers",
            marker=dict(color=color, size=8), name=name, showlegend=True,
            hovertemplate="Simulations: %{x}<br>Score: %{y}<br>Seed: %{customdata[0]}"
                          "<br>Run: %{customdata[1]}<br>%{customdata[2]}%{customdata[3]}<extra></extra>",
        ))
    figure.update_layout(
        template="plotly_dark", paper_bgcolor="#101720", plot_bgcolor="#151f2b",
        font=dict(family="Courier New, monospace", color="#d5dfeb"),
        xaxis_title="Number of simulations", yaxis_title="Current config high score",
        xaxis=dict(rangemode="tozero", **axis_ticks([end])),
        yaxis=dict(rangemode="tozero", **axis_ticks(y)),
        legend=dict(orientation="h", x=.5, xanchor="center", y=-.22, yanchor="top"),
        margin=dict(l=65, r=25, t=30, b=115),
    )
    return {"total": total, "chart": figure.to_html(
        full_html=False, include_plotlyjs=True, div_id="experiment-highscores", default_height="65vh",
        config={"responsive": True, "displaylogo": False},
    )}
