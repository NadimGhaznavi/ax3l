"""Store experiment drafts and run analyses in Ax3l's shared event log."""

from dataclasses import asdict
import json

from ax3l.app.DbMgr import DbMgr
from ax3l.constants.DEventCategory import DEventCategory as Events
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
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
