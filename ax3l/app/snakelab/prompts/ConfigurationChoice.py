"""Present one setting choice with the evidence needed to make it."""

import base64
import json

from ax3l.app.Prompt import Prompt
from ax3l.activity.ConfigurationEvidence import configuration_evidence
from ax3l.constants.DChoice import CHOICE_LABELS
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
from ax3l.entities.SimulationAnalysis import SimulationAnalysis
from ax3l.presentation.snakelab.Templates import templates


class ConfigurationChoice(Prompt):
    def __init__(self, draft: ConfigurationDraft, references: dict[str, SimulationAnalysis],
                 png: bytes | None):
        parameter = draft.next_parameter
        evidence = configuration_evidence(draft, [parameter], references)
        super().__init__(templates.render("prompts/choice.md.jinja", evidence=evidence,
                                         label=CHOICE_LABELS[parameter]))
        self._png = png

    def to_json(self) -> str:
        if self._png is None:
            return super().to_json()
        url = "data:image/png;base64," + base64.b64encode(self._png).decode("ascii")
        return json.dumps({"role": "user", "content": [
            {"type": "text", "text": self.to_md()},
            {"type": "image_url", "image_url": {"url": url}},
        ]}, ensure_ascii=False)
