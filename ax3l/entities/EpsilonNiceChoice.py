"""Explain the custom exploration rule when choosing its pair."""

from ax3l.app.snakelab.prompts.ConfigurationChoice import ConfigurationChoice
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
from ax3l.entities.SimulationAnalysis import SimulationAnalysis
from ax3l.presentation.snakelab.Templates import templates


class EpsilonNiceChoice(ConfigurationChoice):
    def __init__(
        self,
        draft: ConfigurationDraft,
        references: dict[str, SimulationAnalysis],
        png: bytes | None,
    ):
        super().__init__(draft, references, png)
        self._content += "\n\n" + templates.render("prompts/epsilon_nice.md.jinja")
