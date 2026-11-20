"""Stage the next unique seed without accepting a number or running a simulation."""

from copy import deepcopy

from jsonschema import ValidationError

from ax3l.app.snakelab.ExperimentDb import ExperimentDb
from ax3l.app.snakelab.SubmitSingleValueHandler import SubmitSingleValueHandler
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


class RequestSeedChangeHandler(SubmitSingleValueHandler):
    def submit(self, payload: dict) -> dict:
        if not isinstance(payload, dict) or set(payload) != {"draft_id"}:
            return self._reject("Supply exactly draft_id. Ax3l chooses the next seed.")
        draft_id = payload["draft_id"]
        if not isinstance(draft_id, str) or not draft_id:
            return self._reject("draft_id must identify the active configuration draft.")
        experiments = ExperimentDb(self._db)
        draft = experiments.draft()
        if draft is None or draft.draft_id != draft_id:
            return self._reject("This draft is not waiting for a seed change.")
        if "seed" in draft.selections:
            result = self._reject("The seed has already been changed for this draft and cannot be changed again. "
                                  "Choose another available setting, or run the unique configuration.")
            return {**result, "code": "parameter_space_exhausted"}
        if draft.next_parameter != "seed":
            return self._reject("This draft is not waiting for a seed change.")
        candidate = deepcopy(draft.config)
        baseline = self._snake.get_run_result(draft.golden_run_id)["config"]
        while True:
            try:
                candidate["seed"] = SimulationConfiguration.next_seed(candidate["seed"])
            except ValidationError as error:
                return self._reject(f"Cannot increment the seed: {error.message}")
            seed_baseline = {**baseline, "seed": candidate["seed"]}
            if (self._snake.is_config_unique(candidate)
                    and (candidate == seed_baseline or self._snake.is_config_unique(seed_baseline))):
                break
        result = self._save_choice(experiments, draft, "seed", candidate)
        return {**result, "seed": candidate["seed"]}
