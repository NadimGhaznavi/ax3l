"""Immutable observations and the saved interpretation of a completed run."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SimulationAnalysis:
    run_id: str
    config: dict
    metrics: dict
    summary: str
