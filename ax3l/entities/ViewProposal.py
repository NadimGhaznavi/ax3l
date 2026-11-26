"""One view's hypothesis, parameter values, and optional seed request."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ViewProposal:
    hypothesis: str
    values: dict[str, int | float | bool]
