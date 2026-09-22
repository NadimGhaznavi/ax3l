"""Build runtime plots from completed simulations and their LLM conversations."""

from html import escape

import plotly.graph_objects as go


def metrics(history: list[dict]) -> dict:
    if not history:
        return {"chart": None, "total": 0}
    figure = go.Figure()
    for field, name, color in (
        ("runtime_seconds", "Simulation Runtime", "#4c9be8"),
        ("llm_seconds", "LLM Time", "#f09445"),
    ):
        figure.add_trace(go.Scatter(
            x=list(range(1, len(history) + 1)),
            y=[float(row[field]) if row[field] is not None else None for row in history],
            customdata=[escape(row["run_id"]) for row in history],
            mode="lines+markers", name=name, connectgaps=False,
            line=dict(shape="spline", color=color, width=4), marker=dict(size=6),
            hovertemplate="Simulation: %{x}<br>Time: %{y:.3f} s<br>Run: %{customdata}<extra>%{fullData.name}</extra>",
        ))
    figure.update_layout(
        template="plotly_dark", paper_bgcolor="#101720", plot_bgcolor="#151f2b",
        font=dict(family="Courier New, monospace", color="#d5dfeb"),
        xaxis_title="Simulation #", yaxis_title="Time (seconds)",
        xaxis=dict(rangemode="tozero", dtick=1 if len(history) < 20 else None),
        yaxis=dict(rangemode="tozero"),
        legend=dict(orientation="h", x=.5, xanchor="center", y=-.22, yanchor="top"),
        margin=dict(l=65, r=25, t=30, b=115),
    )
    return {"total": len(history), "chart": figure.to_html(
        full_html=False, include_plotlyjs=True, div_id="simulation-runtime", default_height="65vh",
        config={"responsive": True, "displaylogo": False},
    )}
