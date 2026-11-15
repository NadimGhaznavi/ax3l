"""Validate a joint proposal and submit a candidate using the shared workflow."""

from jsonschema import ValidationError

from ax3l.app.snakelab.PairParameters import PAIR_PARAMETERS
from ax3l.app.snakelab.SubmitSingleValueHandler import SubmitSingleValueHandler
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


class SubmitPairValuesHandler(SubmitSingleValueHandler):
    def submit(self, payload: dict) -> dict:
        if not isinstance(payload, dict) or set(payload) != {"pair", "value_1", "value_2"}:
            return self._reject("Supply exactly pair, value_1, and value_2.")
        pair = payload["pair"]
        if not isinstance(pair, str) or pair not in PAIR_PARAMETERS:
            return self._reject(f"pair must be one of {', '.join(PAIR_PARAMETERS)}.")

        changes = []
        descriptions = []
        for index, path in enumerate(PAIR_PARAMETERS[pair], start=1):
            name = f"value_{index}"
            value = payload[name]
            try:
                value = SimulationConfiguration.value(path, value)
            except ValidationError as error:
                return self._reject(f"{name} ({'.'.join(path)}): {error.message}")
            changes.append((path, value))
            descriptions.append(f"{'.'.join(path)}: {value}")

        if pair == "reward_pair":
            try:
                SimulationConfiguration.validate_reward_pair(*(value for _, value in changes))
            except ValidationError as error:
                return self._reject(error.message)
        return self._submit_changes(changes, f"{pair}: " + ", ".join(descriptions))
