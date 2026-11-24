"""One view's next hypothesis and proposed parameter values."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ViewProposal:
    hypothesis: str
    values: dict[str, int | float]
