"""Accept a bounded interpretation and attach exact observations to its run."""

import re
from uuid import UUID

from ax3l.activity.RunAnalysis import measure
from ax3l.app.snakelab.ExperimentDb import ExperimentDb
from ax3l.constants.DSimulationAnalysis import DSimulationAnalysis
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

        if not isinstance(payload, dict) or set(payload) != {"run_id", "section", "summary"}:
            return reject("Supply exactly run_id, section, and summary.")
        run_id, summary = payload["run_id"], payload["summary"]
        section = payload["section"]
        if not isinstance(section, str) or section not in DSimulationAnalysis.SECTIONS:
            return reject("Unknown analysis section.")
        try:
            if not isinstance(run_id, str):
                raise ValueError("run_id must be a UUID")
            UUID(run_id)
        except ValueError:
            return reject("run_id must be a UUID.")
        instruction = "Submit 1–2 sentences using at most 40 words about the assigned chart only."
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 1000:
            return reject(instruction)
        summary = summary.strip()
        if len(summary.split()) > DSimulationAnalysis.MAX_WORDS or len(re.split(r"(?<=[.!?])\s+", summary)) > 2:
            return reject(instruction)
        saved = self._experiments.analysis(run_id)
        if saved is None:
            result = self._snake.get_run_result(run_id)
            if result is None or result["status"] != "completed" or result["high_score"] is None:
                return reject("Analysis requires a completed simulation with a recorded high score.")
            sections = self._experiments.analysis_sections(run_id)
            if section not in sections:
                sections[section] = summary
                if sections.keys() == DSimulationAnalysis.SECTIONS.keys():
                    metrics = measure(self._snake.get_analysis_episodes(run_id), result["high_score"])
                    combined = "\n".join(f"{label}: {sections[name]}"
                                         for name, label in DSimulationAnalysis.SECTIONS.items())
                    self._experiments.save_analysis(SimulationAnalysis(run_id, result["config"], metrics, combined))
                else:
                    self._experiments.save_analysis_sections(run_id, sections)
        return {"status": "ok", "analysis_run_id": run_id}
