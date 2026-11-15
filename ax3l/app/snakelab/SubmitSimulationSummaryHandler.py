"""Accept a bounded interpretation and attach exact observations to its run."""

import re
from uuid import UUID

from ax3l.activity.RunAnalysis import measure
from ax3l.app.snakelab.ExperimentDb import ExperimentDb
from ax3l.entities.SimulationAnalysis import SimulationAnalysis
from ax3l.interface.SnakeLab import SnakeLab


class SubmitSimulationSummaryHandler:
    def __init__(self, db):
        self._experiments = ExperimentDb(db)
        self._snake = SnakeLab()

    def submit(self, payload: dict) -> dict:
        def reject(reason):
            return {"status": "rejected", "code": "invalid_summary", "reason": reason,
                    "source_name": "SimulationSummary", "prompt": {"role": "user", "content": reason}}

        if not isinstance(payload, dict) or set(payload) != {"run_id", "summary"}:
            return reject("Supply exactly run_id and summary.")
        run_id, summary = payload["run_id"], payload["summary"]
        try:
            if not isinstance(run_id, str):
                raise ValueError("run_id must be a UUID")
            UUID(run_id)
        except ValueError:
            return reject("run_id must be a UUID.")
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 1000:
            return reject("Summary must be nonempty text, at most 80 words and 2–3 sentences.")
        summary = summary.strip()
        if len(summary.split()) > 80 or not 2 <= len(re.split(r"(?<=[.!?])\s+", summary)) <= 3:
            return reject("Submit 2–3 sentences using at most 80 words.")
        saved = self._experiments.analysis(run_id)
        if saved is None:
            result = self._snake.get_run_result(run_id)
            if result is None or result["status"] != "completed" or result["high_score"] is None:
                return reject("Analysis requires a completed simulation with a recorded high score.")
            metrics = measure(self._snake.get_analysis_episodes(run_id), result["high_score"])
            self._experiments.save_analysis(SimulationAnalysis(run_id, result["config"], metrics, summary))
        return {"status": "ok", "analysis_run_id": run_id}
