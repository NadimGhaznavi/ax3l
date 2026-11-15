"""Present comparable safe-exploration pairs."""

import json

from ax3l.app.DynamicPrompt import DynamicPrompt
from ax3l.interface.SnakeLab import SnakeLab


class ComparisonEpsilonNicePair(DynamicPrompt):
    def __init__(self, current_golden_run_id: str):
        self._current_golden_run_id = current_golden_run_id
        self._snake = SnakeLab()
        super().__init__()

    def refresh(self) -> None:
        baseline = self._snake.get_run_result(self._current_golden_run_id)
        report = {
            "gold": {**baseline["config"]["epsilon_nice"], "high_score": baseline["high_score"]},
            "epsilon": baseline["config"]["epsilon"],
            "results": self._snake.get_epsilon_nice_report(self._current_golden_run_id),
        }
        self._content = (
            f"```json\n{json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2)}\n```\n"
            "Results are sorted by probability, steps, and completed-run high scores "
            "across seeds. All other settings, including the ordinary epsilon schedule, "
            "match gold. Empty scores mean no completed scored runs for that combination."
        )
