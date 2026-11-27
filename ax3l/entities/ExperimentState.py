"""A durable single-view experiment within a shuffled round."""

from dataclasses import dataclass, field

from ax3l.entities.ViewHistory import ViewHistory
from ax3l.entities.ViewProposal import ViewProposal


@dataclass
class ExperimentState:
    experiment_id: str
    phase: str
    config: dict
    baseline: bool = False
    seed_baseline: bool = False
    golden_run_id: str | None = None
    latest_run_id: str | None = None
    reference_run_id: str | None = None
    golden_history: ViewHistory | None = None
    failures: int = 0
    order: list[str] = field(default_factory=list)
    view_index: int = 0
    proposals: dict[str, ViewProposal] = field(default_factory=dict)
    observations: dict[str, str] = field(default_factory=dict)
    run_id: str | None = None
    preceding_match: str | None = None

    @property
    def view_name(self) -> str:
        return self.order[self.view_index]
