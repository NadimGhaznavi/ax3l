"""The durable choices for one complete simulation configuration."""

from dataclasses import dataclass, field

from ax3l.app.snakelab.SingleParameters import SINGLE_PARAMETERS
from ax3l.app.snakelab.PairParameters import PAIR_PARAMETERS


PARAMETER_ORDER = list(SINGLE_PARAMETERS) + list(PAIR_PARAMETERS) + ["seed"]


@dataclass
class ConfigurationDraft:
    draft_id: str
    golden_run_id: str
    references: dict[str, str]
    config: dict
    selections: list[str] = field(default_factory=list)
    phase: str = "selecting_parameter"
    run_id: str | None = None
    parameter: str | None = None
    decision_expires_at: float | None = None  # UTC Unix deadline for status reporting.

    @property
    def next_parameter(self) -> str | None:
        if self.phase != "choosing":
            return None
        return self.parameter
