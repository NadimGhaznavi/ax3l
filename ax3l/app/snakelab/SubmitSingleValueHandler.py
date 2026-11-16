"""Validate and durably stage one parameter choice without running a simulation."""

from copy import deepcopy
import json
from jsonschema import ValidationError

from ax3l.app.snakelab.SingleParameters import SINGLE_PARAMETERS
from ax3l.app.DbMgr import DbMgr
from ax3l.app.snakelab.ExperimentDb import ExperimentDb
from ax3l.app.snakelab.prompts.InvalidValue import InvalidValue
from ax3l.app.snakelab.prompts.NoDupes import NoDupes
from ax3l.constants.DEventCategory import DEventCategory
from ax3l.constants.DChoice import CHOICE_LABELS
from ax3l.entities.ConfigurationDraft import PARAMETER_ORDER
from ax3l.interface.SnakeLab import SnakeLab
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


class SubmitSingleValueHandler:
    def __init__(self, db: DbMgr):
        self._db = db
        self._snake = SnakeLab()

    def _reject(self, reason: str) -> dict:
        category = DEventCategory.Configuration
        prompt = InvalidValue(reason)
        self._db.log(
            category.PROPOSAL_INVALID, category.CATEGORY, "INFO", prompt.to_md(),
        )
        return {"status": "rejected", "reason": reason,
                "code": "invalid_value",
                "prompt": json.loads(prompt.to_json()), "source_name": prompt.source_name}

    def submit(self, payload: dict) -> dict:
        if not isinstance(payload, dict) or set(payload) != {"draft_id", "parameter", "value"}:
            return self._reject("Supply exactly draft_id, parameter, and value.")
        parameter, value = payload["parameter"], payload["value"]
        if not isinstance(parameter, str) or not parameter:
            return self._reject("parameter must be a JSON spec key.")

        if parameter == "seed":
            return self._reject("Seed is managed by Ax3l and cannot be proposed.")
        if parameter not in SINGLE_PARAMETERS:
            return self._reject(f"Parameter is not in the single-parameter search space: {parameter}.")
        path, _ = SINGLE_PARAMETERS[parameter]
        try:
            value = SimulationConfiguration.value(path, value)
        except ValidationError as error:
            return self._reject(f"{CHOICE_LABELS[parameter]}: {error.message}")

        return self._stage_changes(payload["draft_id"], parameter, [(path, value)])

    def _stage_changes(self, draft_id: str, parameter: str, changes: list) -> dict:
        """Save a choice; only a complete candidate is checked for duplicates."""
        if not isinstance(draft_id, str) or not draft_id:
            return self._reject("draft_id must identify the active configuration draft.")
        experiments = ExperimentDb(self._db)
        draft = experiments.draft()
        if draft is None or draft.draft_id != draft_id or draft.next_parameter != parameter:
            return self._reject("This choice does not match the active draft's next parameter.")
        candidate = deepcopy(draft.config)
        for path, value in changes:
            node = candidate
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = value
        SimulationConfiguration.validate(candidate)
        selections = draft.selections + [parameter]
        if len(selections) == len(PARAMETER_ORDER):
            draft.phase = "ready" if self._snake.is_config_unique(candidate) else "selecting_parameter"
        draft.config = candidate
        draft.selections = selections
        experiments.save_draft(draft)
        if draft.phase == "selecting_parameter":
            category = DEventCategory.Configuration
            self._db.log(category.PROPOSAL_DUPLICATE, category.CATEGORY, "INFO", NoDupes(draft).to_md(),
                         process_id=draft.draft_id)
        return {"status": "ok", "draft_id": draft.draft_id, "phase": draft.phase}
