"""Measured data and any previously saved observation for a completed run."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SimulationAnalysis:
    run_id: str
    config: dict
    metrics: dict
    summary: str | None
