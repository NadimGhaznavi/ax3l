"""Let Qwen choose a setting that has not yet been changed in the current draft."""

from ax3l.app.snakelab.ExperimentDb import ExperimentDb
from ax3l.app.snakelab.SubmitSingleValueHandler import SubmitSingleValueHandler
from ax3l.constants.DChoice import CHOICE_LABELS
from ax3l.entities.ConfigurationDraft import PARAMETER_ORDER


class SelectParameterHandler(SubmitSingleValueHandler):
    def submit(self, payload: dict) -> dict:
        if not isinstance(payload, dict) or set(payload) != {"draft_id", "parameter"}:
            return self._reject("Supply exactly draft_id and parameter.")
        parameter, draft_id = payload["parameter"], payload["draft_id"]
        if not isinstance(parameter, str) or parameter not in PARAMETER_ORDER:
            return self._reject("parameter must be one of " + ", ".join(PARAMETER_ORDER) + ".")
        if not isinstance(draft_id, str) or not draft_id:
            return self._reject("draft_id must identify the active configuration draft.")
        experiments = ExperimentDb(self._db)
        draft = experiments.draft()
        if draft is None or draft.draft_id != draft_id or draft.phase not in ("selecting_parameter", "reviewing"):
            return self._reject("This draft is not waiting for a parameter selection.")
        if parameter in draft.selections:
            if parameter == "seed":
                result = self._reject("The seed has already been changed for this draft and cannot be changed again. "
                                      "Choose another available setting, or run the unique configuration.")
                return {**result, "code": "parameter_space_exhausted"}
            return self._reject(f"{parameter} has already been chosen in this experiment. "
                                "Choose an unused parameter or run the unique configuration.")
        if not self._snake.available_parameters(draft.config, [parameter]):
            result = self._reject(f"No untested changes remain for {CHOICE_LABELS[parameter]} with the current "
                                  "seed and other draft settings. Choose another available setting, "
                                  "or run the unique configuration.")
            return {**result, "code": "parameter_space_exhausted"}
        draft.parameter = parameter
        draft.phase = "choosing"
        experiments.save_draft(draft)
        return {"status": "ok", "draft_id": draft.draft_id, "phase": draft.phase}
