"""Present one setting choice with the evidence needed to make it."""

import base64
import json

from ax3l.app.Prompt import Prompt
from ax3l.activity.ConfigurationEvidence import choice_context
from ax3l.app.snakelab.PairParameters import PAIR_PARAMETERS
from ax3l.constants.DChoice import CHOICE_LABELS
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
from ax3l.entities.SimulationAnalysis import SimulationAnalysis
from ax3l.interface.KnowledgeBase import KnowledgeBase
from ax3l.presentation.snakelab.Templates import templates


class ConfigurationChoice(Prompt):
    def __init__(self, draft: ConfigurationDraft, references: dict[str, SimulationAnalysis],
                 chart_scope: str, png: bytes | None):
        parameter = draft.next_parameter
        tool = "submit_pair_values" if parameter in PAIR_PARAMETERS else "submit_single_value"
        context = choice_context(draft, references, chart_scope, png is not None)
        super().__init__(templates.render("prompts/choice.md.jinja", **context,
                                         label=CHOICE_LABELS[parameter], tool=tool,
                                         selection=KnowledgeBase().read("/guides/selection")))
        self._png = png

    def to_json(self) -> str:
        if self._png is None:
            return super().to_json()
        url = "data:image/png;base64," + base64.b64encode(self._png).decode("ascii")
        return json.dumps({"role": "user", "content": [
            {"type": "text", "text": self.to_md()},
            {"type": "image_url", "image_url": {"url": url}},
        ]}, ensure_ascii=False)
