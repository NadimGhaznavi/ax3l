"""The last recorded image-analysis task for a simulation."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisTask:
    run_id: str
    section: str
    phase: str
