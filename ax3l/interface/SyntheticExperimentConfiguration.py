"""Load the editable first experiment and its four hypotheses."""

import json
from pathlib import Path

from ax3l.activity.ViewConfiguration import view_values
from ax3l.constants.DViewConversation import DViewConversation
from ax3l.entities.ExperimentView import VIEWS
from ax3l.entities.ViewProposal import ViewProposal
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


def _nonfinite(value: str):
    raise ValueError(f"Nonfinite JSON number: {value}")


class SyntheticExperimentConfiguration:
    @staticmethod
    def load(directory: Path | None = None) -> dict[str, ViewProposal]:
        directory = directory if directory is not None else Path(__file__).resolve().parents[2] / "conf/synthetic"
        path = directory / "config.json"
        try:
            config = json.loads(path.read_text(), parse_constant=_nonfinite)
        except ValueError as error:
            raise ValueError(f"{path}: {error}") from error
        baseline = SimulationConfiguration.defaults()
        if config["seed"] != baseline["seed"]:
            raise ValueError(f"{path}: seed must match the default baseline seed ({baseline['seed']}).")
        if config == baseline:
            raise ValueError(f"{path}: change at least one per-view parameter from the default baseline.")

        proposals = {}
        for name, view in VIEWS.items():
            path = directory / f"{name}.md"
            hypothesis = path.read_text().strip()
            if not hypothesis or len(hypothesis) > DViewConversation.HYPOTHESIS_MAX_LENGTH:
                raise ValueError(f"{path}: hypothesis must contain 1 to "
                                 f"{DViewConversation.HYPOTHESIS_MAX_LENGTH} characters of nonblank text.")
            proposals[name] = ViewProposal(hypothesis, view_values(view, config))
        return proposals
