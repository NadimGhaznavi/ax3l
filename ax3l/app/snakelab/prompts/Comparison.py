"""Present every simulation's learning rate and high score, ordered by LR."""

import json

from ax3l.app.DynamicPrompt import DynamicPrompt
from ax3l.interface.SnakeLab import SnakeLab


class Comparison(DynamicPrompt):
    def __init__(self, golden_run_id: str, latest_run_id: str, current_golden_run_id: str):
        self._golden_run_id = golden_run_id
        self._latest_run_id = latest_run_id
        self._current_golden_run_id = current_golden_run_id
        self._snake = SnakeLab()
        super().__init__()

    def refresh(self) -> None:
        history = self._snake.get_learning_rate_history()
        self._content = (
            "Compare the simulation results and choose the next learning rate to improve high score.\n"
            f"Golden run before comparison: {self._golden_run_id}\n"
            f"Latest simulation: {self._latest_run_id}\n"
            f"Current golden run: {self._current_golden_run_id}\n"
            "The current golden run is the baseline for the next submission. "
            "A strictly higher high score wins; ties retain the existing golden run.\n\n"
            "All simulations, ordered by learning rate (null high_score means no score recorded):\n"
            f"```json\n{json.dumps(history, indent=2, ensure_ascii=False, allow_nan=False)}\n```"
        )
