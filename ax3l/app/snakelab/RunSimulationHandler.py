"""Check the saved configuration for duplicates before accepting Qwen's run decision."""

import json

from ax3l.app.Prompt import Prompt
from ax3l.app.snakelab.ExperimentDb import ExperimentDb
from ax3l.app.snakelab.SubmitSingleValueHandler import SubmitSingleValueHandler
from ax3l.constants.DEventCategory import DEventCategory as Events
from ax3l.presentation.snakelab.Templates import templates


class RunSimulationHandler(SubmitSingleValueHandler):
    def submit(self, payload: dict) -> dict:
        if not isinstance(payload, dict) or set(payload) != {"draft_id"}:
            return self._reject("Supply exactly draft_id.")
        draft_id = payload["draft_id"]
        if not isinstance(draft_id, str) or not draft_id:
            return self._reject("draft_id must identify the active configuration draft.")
        experiments = ExperimentDb(self._db)
        draft = experiments.draft()
        if (draft is None or draft.draft_id != draft_id
                or draft.phase not in ("selecting_parameter", "choosing", "reviewing")):
            return self._reject("This draft is not accepting configuration decisions.")
        if not self._snake.is_config_unique(draft.config):
            prompt = Prompt(templates.render("prompts/run_duplicate.md.jinja"))
            self._db.log(Events.Configuration.PROPOSAL_DUPLICATE, Events.Configuration.CATEGORY,
                         "INFO", prompt.to_md(), process_id=draft.draft_id)
            return {"status": "rejected", "code": "duplicate_configuration", "reason": prompt.to_md(),
                    "prompt": json.loads(prompt.to_json()), "source_name": "RunSimulationHandler"}
        draft.phase = "ready"
        draft.parameter = None
        experiments.save_draft(draft)
        return {"status": "ok", "draft_id": draft.draft_id, "phase": draft.phase}
