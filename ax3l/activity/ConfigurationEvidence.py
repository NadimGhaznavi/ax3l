"""Prepare measured choice evidence without formatting conversation text."""

from ax3l.app.snakelab.ParameterSpace import parameter_values
from ax3l.app.snakelab.PairParameters import PAIR_PARAMETERS
from ax3l.activity.SimulationDataValues import run_comparison_values
from ax3l.constants.DChoice import CHOICE_LABELS
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
from ax3l.entities.SimulationAnalysis import SimulationAnalysis


def _setting_value(config: dict, parameter: str) -> int | float | dict:
    values = parameter_values(config, parameter)
    return values if parameter in PAIR_PARAMETERS else values[parameter]


def configuration_evidence(draft: ConfigurationDraft, parameters: list[str],
                           references: dict[str, SimulationAnalysis]) -> dict:
    runs = {scope: references[scope] for scope in ("best", "golden", "latest")}
    settings = {}
    for parameter in parameters:
        values = {scope: _setting_value(run.config, parameter) for scope, run in runs.items()}
        values["draft"] = _setting_value(draft.config, parameter)
        settings[parameter] = dict(label=CHOICE_LABELS[parameter], values=values)
    return dict(settings=settings, results=run_comparison_values(draft, runs))
