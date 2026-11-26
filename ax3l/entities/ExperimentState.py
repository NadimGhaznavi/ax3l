"""A durable configuration cycle and its four result evaluations."""

from dataclasses import dataclass, field

from ax3l.entities.ViewProposal import ViewProposal


@dataclass
class ExperimentState:
    experiment_id: str
    phase: str
    config: dict
    baseline: bool = False
    golden_run_id: str | None = None
    latest_run_id: str | None = None
    reference_run_id: str | None = None
    order: list[str] = field(default_factory=list)
    previous: dict[str, ViewProposal] = field(default_factory=dict)
    previous_seeded: bool = True
    proposals: dict[str, ViewProposal] = field(default_factory=dict)
    observations: dict[str, str] = field(default_factory=dict)
    run_id: str | None = None
    preceding_match: str | None = None
    new_seed: bool = False
    seed_baseline: bool = False
