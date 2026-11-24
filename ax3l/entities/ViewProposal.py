"""One view's assessment and proposed experiment."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ViewProposal:
    evaluation: str
    hypothesis: str
    expected_effect: str
    values: dict[str, int | float]
