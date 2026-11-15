"""Store experiment drafts and run analyses in Ax3l's shared event log."""

from dataclasses import asdict
import json

from ax3l.app.DbMgr import DbMgr
from ax3l.constants.DEventCategory import DEventCategory as Events
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
from ax3l.entities.AnalysisTask import AnalysisTask
from ax3l.entities.SimulationAnalysis import SimulationAnalysis


class ExperimentDb:
    def __init__(self, db: DbMgr):
        self._db = db

    def _latest(self, category: str, name: str, process_id: str | None = None) -> dict | None:
        rows = self._db.query("""
            SELECT m.content FROM events e JOIN event_messages m USING (event_id)
            WHERE e.category = %s AND e.name = %s AND (%s IS NULL OR e.process_id = %s)
            ORDER BY e.event_id DESC LIMIT 1
        """, (category, name, process_id, process_id))
        return json.loads(rows[0]["content"]) if rows else None

    def draft(self, draft_id: str | None = None) -> ConfigurationDraft | None:
        data = self._latest(Events.Configuration.CATEGORY, Events.Configuration.DRAFT_SAVED, draft_id)
        return ConfigurationDraft(**data) if data is not None else None

    def last_completed_draft(self) -> ConfigurationDraft | None:
        """Keep the last finished proposal available after a new draft starts."""
        rows = self._db.query("""
            SELECT m.content FROM events e JOIN event_messages m USING (event_id)
            WHERE e.category = %s AND e.name = %s
              AND JSON_UNQUOTE(JSON_EXTRACT(m.content, '$.phase')) = 'completed'
            ORDER BY e.event_id DESC LIMIT 1
        """, (Events.Configuration.CATEGORY, Events.Configuration.DRAFT_SAVED))
        return ConfigurationDraft(**json.loads(rows[0]["content"])) if rows else None

    def save_draft(self, draft: ConfigurationDraft) -> None:
        self._db.log(Events.Configuration.DRAFT_SAVED, Events.Configuration.CATEGORY,
                     "INFO", json.dumps(asdict(draft), allow_nan=False), process_id=draft.draft_id)

    def analysis(self, run_id: str) -> SimulationAnalysis | None:
        data = self._latest(Events.SnakeLab.CATEGORY, Events.SnakeLab.ANALYZED, run_id)
        return SimulationAnalysis(**data) if data is not None else None

    def save_analysis(self, analysis: SimulationAnalysis) -> None:
        self._db.log(Events.SnakeLab.ANALYZED, Events.SnakeLab.CATEGORY, "INFO",
                     json.dumps(asdict(analysis), allow_nan=False), process_id=analysis.run_id)

    def analysis_sections(self, run_id: str) -> dict[str, str]:
        data = self._latest(Events.SnakeLab.CATEGORY, Events.SnakeLab.ANALYSIS_PROGRESS, run_id)
        return data if data is not None else {}

    def save_analysis_sections(self, run_id: str, sections: dict[str, str]) -> None:
        self._db.log(Events.SnakeLab.ANALYSIS_PROGRESS, Events.SnakeLab.CATEGORY, "INFO",
                     json.dumps(sections, allow_nan=False), process_id=run_id)

    def save_analysis_task(self, task: AnalysisTask) -> None:
        self._db.log(Events.SnakeLab.ANALYSIS_TASK, Events.SnakeLab.CATEGORY, "INFO",
                     json.dumps(asdict(task), allow_nan=False), process_id=task.run_id)

    def analysis_states(self, run_ids: list[str]) -> dict[str, dict]:
        """Read each run's saved analysis, sections, and task in one snapshot."""
        states = {run_id: dict(analysis=None, sections={}, task=None) for run_id in run_ids}
        if not run_ids:
            return states
        placeholders = ", ".join("%s" for _ in run_ids)
        category = Events.SnakeLab
        rows = self._db.query(f"""
            SELECT latest.process_id, latest.name, m.content FROM (
                SELECT process_id, name, MAX(event_id) AS event_id FROM events
                WHERE category = %s AND name IN (%s, %s, %s)
                  AND process_id IN ({placeholders})
                GROUP BY process_id, name
            ) latest JOIN event_messages m USING (event_id)
        """, (category.CATEGORY, category.ANALYZED, category.ANALYSIS_PROGRESS,
              category.ANALYSIS_TASK, *run_ids))
        for row in rows:
            state = states[row["process_id"]]
            data = json.loads(row["content"])
            if row["name"] == category.ANALYZED:
                state["analysis"] = SimulationAnalysis(**data)
            elif row["name"] == category.ANALYSIS_TASK:
                state["task"] = AnalysisTask(**data)
            else:
                state["sections"] = data
        return states

    def comparison(self, run_id: str) -> dict | None:
        rows = self._db.query("""
            SELECT e.event_id, m.content FROM events e JOIN event_messages m USING (event_id)
            WHERE e.category = %s AND e.name = %s AND e.process_id = %s
            ORDER BY e.event_id DESC LIMIT 1
        """, (Events.Configuration.CATEGORY, Events.Configuration.COMPARED, run_id))
        return {**json.loads(rows[0]["content"]), "event_id": rows[0]["event_id"]} if rows else None

    def submission_events(self, run_id: str) -> dict[str, int]:
        rows = self._db.query("""
            SELECT name, event_id FROM events WHERE process_id = %s AND
                ((category = %s AND name = %s) OR (category = %s AND name = %s))
        """, (run_id, Events.Configuration.CATEGORY, Events.Configuration.PROPOSAL_ACCEPTED,
               Events.SnakeLab.CATEGORY, Events.SnakeLab.SUBMITTED))
        return {row["name"]: row["event_id"] for row in rows}
