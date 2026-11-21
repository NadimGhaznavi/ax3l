"""Overlay the previous golden run and latest simulation's episode losses."""

import base64
from uuid import UUID

import plotly.graph_objects as go

from ax3l.activity.PlotTicks import axis_ticks
from ax3l.app.ideas.prompts.LossPlot import LossPlot
from ax3l.constants.DLossPlot import DLossPlot


class ComparisonPlot(LossPlot):
    def __init__(self, golden_run_id: str, latest_run_id: str):
        UUID(latest_run_id)
        self._latest_run_id = latest_run_id
        super().__init__(golden_run_id)

    def refresh(self) -> None:
        figure = go.Figure()
        for run_id, label in ((self._run_id, "Golden before comparison"),
                              (self._latest_run_id, "Latest simulation")):
            losses = self._snake_lab.get_episode_losses(run_id)
            if not any(loss is not None for _, loss in losses):
                raise ValueError(f"No training losses recorded for simulation {run_id}")
            figure.add_trace(go.Scatter(
                x=[episode for episode, _ in losses], y=[loss for _, loss in losses],
                mode="lines", name=label, line=dict(width=2), connectgaps=False,
            ))
        figure.update_layout(
            title="Training Loss Comparison", xaxis_title="Episode", yaxis_title="Loss",
            template="plotly_dark", width=DLossPlot.WIDTH, height=DLossPlot.HEIGHT,
            margin=dict(l=70, r=30, t=80, b=70),
            legend=dict(orientation="h", y=1.15, x=0),
        )
        figure.update_xaxes(**axis_ticks(value for trace in figure.data for value in trace.x))
        png = figure.to_image(format="png", scale=DLossPlot.SCALE)
        self._image_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        self._content = "Compare latest with golden."
