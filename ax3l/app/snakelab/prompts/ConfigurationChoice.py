"""Present saved reference analyses, the draft, and the assigned choice."""

import json

from ax3l.app.Prompt import Prompt
from ax3l.app.snakelab.PairParameters import PAIR_PARAMETERS, pair_instructions
from ax3l.app.snakelab.SingleParameters import parameter_instructions
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
from ax3l.entities.SimulationAnalysis import SimulationAnalysis


class ConfigurationChoice(Prompt):
    def __init__(self, draft: ConfigurationDraft, analyses: dict[str, SimulationAnalysis]):
        references = []
        roles = {}
        for role, run_id in draft.references.items():
            roles.setdefault(run_id, []).append(role)
        target = analyses[draft.golden_run_id].metrics["high_score"]
        for run_id, labels in roles.items():
            analysis = analyses[run_id]
            references.append({"roles": labels, "run": run_id.split('-')[0],
                               "config": analysis.config, "metrics": analysis.metrics,
                               "difference_from_target": analysis.metrics["high_score"] - target,
                               "interpretation": analysis.summary})
        parameter = draft.next_parameter
        instructions = (pair_instructions(parameter) if parameter in PAIR_PARAMETERS
                        else parameter_instructions(parameter))
        tool = "submit_pair_values" if parameter in PAIR_PARAMETERS else "submit_single_value"
        super().__init__(
            f"Goal: exceed the current golden high score of {target} points on seed {draft.config['seed']}. "
            "Latest is feedback; golden is the current-seed baseline; all-time best is historical context. "
            "Scores from different seeds are not controlled comparisons.\n"
            f"Reference simulation analyses:\n{json.dumps(references, allow_nan=False)}\n"
            f"Current draft configuration:\n{json.dumps(draft.config, allow_nan=False)}\n"
            f"Already selected: {', '.join(draft.selections) or 'none'}.\n"
            f"Choose {parameter}. {instructions}\n"
            f"Call {tool} to save this choice in the draft. Keeping a value unchanged is allowed. "
            "All tunable settings must be selected before Ax3l runs one simulation. "
            "Account for earlier draft choices when selecting this value."
        )
