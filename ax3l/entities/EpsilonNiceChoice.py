"""Explain the custom exploration rule when choosing its pair."""

from ax3l.app.snakelab.prompts.ConfigurationChoice import ConfigurationChoice
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
from ax3l.entities.SimulationAnalysis import SimulationAnalysis


class EpsilonNiceChoice(ConfigurationChoice):
    def __init__(
        self,
        draft: ConfigurationDraft,
        latest: SimulationAnalysis,
        golden: SimulationAnalysis,
        chart_scope: str,
        png: bytes | None,
    ):
        super().__init__(draft, latest, golden, chart_scope, png)
        self._content += (
            "\n\nEpsilonNice applies after ordinary epsilon exploration ends.\n"
            "On each eligible move outside a detour, value_1 is the chance "
            "of starting a detour on the next move.\n"
            "A detour lasts value_2 moves.\n"
            "On each detour move, the snake takes an immediately safe alternative "
            "to the model's pick if one exists.\n"
            "Each episode starts with no active detour."
        )
