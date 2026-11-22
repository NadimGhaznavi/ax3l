"""Prepare measured choice evidence without formatting conversation text."""

from ax3l.app.snakelab.ParameterSpace import parameter_values
from ax3l.app.snakelab.PairParameters import PAIR_PARAMETERS
from ax3l.activity.SimulationDataValues import draft_values, run_snapshot_values
from ax3l.constants.DChoice import CHOICE_CHARTS, CHOICE_LABELS
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
    target = runs["golden"].metrics["high_score"]
    return dict(settings=settings,
                runs={scope: run_snapshot_values(scope, draft, run, target) for scope, run in runs.items()},
                draft=draft_values(draft))


def choice_context(draft: ConfigurationDraft, references: dict[str, SimulationAnalysis],
                   chart_scope: str, has_image: bool) -> dict:
    parameter = draft.next_parameter
    chart = CHOICE_CHARTS.get(parameter)
    return dict(evidence=configuration_evidence(draft, [parameter], references),
                chart=chart, chart_scope=chart_scope, has_image=has_image,
                golden_has_loss=bool(references["golden"].metrics["episodes_with_loss"]) if chart == "loss" else False)
