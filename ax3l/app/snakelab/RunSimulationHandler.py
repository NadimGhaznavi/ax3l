"""Save Qwen's decision to run a configuration already checked for uniqueness."""

from ax3l.app.snakelab.ExperimentDb import ExperimentDb
from ax3l.app.snakelab.SubmitSingleValueHandler import SubmitSingleValueHandler


class RunSimulationHandler(SubmitSingleValueHandler):
    def submit(self, payload: dict) -> dict:
        if not isinstance(payload, dict) or set(payload) != {"draft_id"}:
            return self._reject("Supply exactly draft_id.")
        draft_id = payload["draft_id"]
        if not isinstance(draft_id, str) or not draft_id:
            return self._reject("draft_id must identify the active configuration draft.")
        experiments = ExperimentDb(self._db)
        draft = experiments.draft()
        if draft is None or draft.draft_id != draft_id or draft.phase != "reviewing":
            return self._reject("Only a unique configuration awaiting Qwen's decision can be run.")
        draft.phase = "ready"
        experiments.save_draft(draft)
        return {"status": "ok", "draft_id": draft.draft_id, "phase": draft.phase}
