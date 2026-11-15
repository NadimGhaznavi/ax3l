"""Validate and stage a pair of configuration choices together."""

from jsonschema import ValidationError

from ax3l.app.snakelab.PairParameters import PAIR_PARAMETERS
from ax3l.app.snakelab.SubmitSingleValueHandler import SubmitSingleValueHandler
from ax3l.constants.DChoice import PAIR_LABELS
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


class SubmitPairValuesHandler(SubmitSingleValueHandler):
    def submit(self, payload: dict) -> dict:
        if not isinstance(payload, dict) or set(payload) != {"draft_id", "pair", "value_1", "value_2"}:
            return self._reject("Supply exactly draft_id, pair, value_1, and value_2.")
        pair = payload["pair"]
        if not isinstance(pair, str) or pair not in PAIR_PARAMETERS:
            return self._reject(f"pair must be one of {', '.join(PAIR_PARAMETERS)}.")

        changes = []
        for index, path in enumerate(PAIR_PARAMETERS[pair], start=1):
            name = f"value_{index}"
            value = payload[name]
            try:
                value = SimulationConfiguration.value(path, value)
            except ValidationError as error:
                return self._reject(f"{name} ({PAIR_LABELS[pair][index - 1]}): {error.message}")
            changes.append((path, value))

        if pair == "reward_pair":
            try:
                SimulationConfiguration.validate_reward_pair(*(value for _, value in changes))
            except ValidationError as error:
                return self._reject(error.message)
        return self._stage_changes(payload["draft_id"], pair, changes)
