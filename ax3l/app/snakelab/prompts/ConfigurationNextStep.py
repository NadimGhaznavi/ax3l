"""Ask Qwen which parameter to change or whether to run a unique draft."""

from ax3l.app.Prompt import Prompt
from ax3l.activity.ConfigurationEvidence import configuration_evidence
from ax3l.entities.ConfigurationDraft import ConfigurationDraft, PARAMETER_ORDER
from ax3l.entities.SimulationAnalysis import SimulationAnalysis
from ax3l.presentation.snakelab.Templates import templates


class ConfigurationNextStep(Prompt):
    def __init__(self, draft: ConfigurationDraft, parameters: list[str],
                 references: dict[str, SimulationAnalysis]):
        evidence = configuration_evidence(draft, PARAMETER_ORDER, references)
        for parameter, setting in evidence["settings"].items():
            setting["editable"] = parameter in parameters
        super().__init__(templates.render("prompts/next_step.md.jinja", can_edit=bool(parameters),
                                         settings=evidence["settings"], runs=evidence["runs"]))
