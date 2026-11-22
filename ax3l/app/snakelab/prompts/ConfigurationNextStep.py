"""Ask Qwen which parameter to change or whether to run a unique draft."""

from ax3l.app.Prompt import Prompt
from ax3l.activity.ConfigurationEvidence import configuration_evidence
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
from ax3l.entities.SimulationAnalysis import SimulationAnalysis
from ax3l.presentation.snakelab.Templates import templates


class ConfigurationNextStep(Prompt):
    def __init__(self, draft: ConfigurationDraft, parameters: list[str],
                 references: dict[str, SimulationAnalysis]):
        evidence = configuration_evidence(draft, parameters, references)
        choices = evidence["settings"]
        if draft.phase == "reviewing" and not choices:
            action = "run"
        elif draft.phase == "reviewing":
            action = "review"
        elif draft.selections:
            action = "revise"
        else:
            action = "select"
        super().__init__(templates.render("prompts/next_step.md.jinja", action=action,
                                         choices=choices, evidence=evidence))
