"""The evidence produced by the view that owns the current golden configuration."""

from dataclasses import dataclass

from ax3l.entities.ViewProposal import ViewProposal


@dataclass
class ViewHistory:
    view: str
    proposal: ViewProposal
    reference_run_id: str
    latest_run_id: str
    observations: str
