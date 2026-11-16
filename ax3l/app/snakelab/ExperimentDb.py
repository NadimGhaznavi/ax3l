"""Store experiment drafts and run analyses in Ax3l's shared event log."""

from dataclasses import asdict
import json

from ax3l.app.DbMgr import DbMgr
from ax3l.constants.DEventCategory import DEventCategory as Events
from ax3l.entities.ConfigurationDraft import ConfigurationDraft, PARAMETER_ORDER
from ax3l.entities.AnalysisTask import AnalysisTask
from ax3l.entities.SimulationAnalysis import SimulationAnalysis


def _restore_draft(data: dict) -> ConfigurationDraft:
    """Resume snapshots saved before Qwen chose the parameter order."""
    if "parameter" not in data:
        data = dict(data)
        if data["phase"] == "choosing":
            data["parameter"] = next(parameter for parameter in PARAMETER_ORDER if parameter not in data["selections"])
        elif data["phase"] == "preparing" and data["selections"] and len(data["selections"]) < len(PARAMETER_ORDER):
            data["parameter"] = next(parameter for parameter in PARAMETER_ORDER if parameter not in data["selections"])
            data["phase"] = "choosing"
        elif data["phase"] == "ready":
            data["phase"] = "reviewing"
    return ConfigurationDraft(**data)


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
        return _restore_draft(data) if data is not None else None

    def last_completed_draft(self) -> ConfigurationDraft | None:
        """Keep the last finished proposal available after a new draft starts."""
        rows = self._db.query("""
            SELECT m.content FROM events e JOIN event_messages m USING (event_id)
            WHERE e.category = %s AND e.name = %s
              AND JSON_UNQUOTE(JSON_EXTRACT(m.content, '$.phase')) = 'completed'
            ORDER BY e.event_id DESC LIMIT 1
        """, (Events.Configuration.CATEGORY, Events.Configuration.DRAFT_SAVED))
        return _restore_draft(json.loads(rows[0]["content"])) if rows else None

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

    def activity_events(self, process_ids: list[str]) -> list[dict]:
        """Read work metadata without transferring the embedded chart images."""
        if not process_ids:
            return []
        placeholders = ", ".join("%s" for _ in process_ids)
        rows = self._db.query(f"""
            SELECT e.event_id, e.occurred_at, CURRENT_TIMESTAMP(6) AS observed_at,
                   e.process_id, e.parent_event_id,
                   e.name, e.parameter, e.source_name,
                   CASE WHEN e.name = %s THEN m.content END AS task,
                   CASE WHEN e.name = %s AND JSON_VALID(m.content)
                        THEN JSON_EXTRACT(m.content, '$.usage.total_tokens') END AS tokens
            FROM events e JOIN event_messages m USING (event_id)
            WHERE e.process_id IN ({placeholders}) AND
                ((e.category = %s AND e.name = %s) OR
                 (e.category = %s AND e.name IN (%s, %s, %s, %s)))
            ORDER BY e.event_id
        """, (Events.SnakeLab.ANALYSIS_TASK, Events.Conversation.RESPONSE, *process_ids,
              Events.SnakeLab.CATEGORY, Events.SnakeLab.ANALYSIS_TASK,
              Events.Conversation.CATEGORY, Events.Conversation.STARTED, Events.Conversation.PROMPT,
              Events.Conversation.RESPONSE, Events.Conversation.ENDED))
        for row in rows:
            row["task"] = json.loads(row["task"]) if row["task"] is not None else None
            row["tokens"] = json.loads(row["tokens"]) if row["tokens"] is not None else None
            if row["tokens"] is not None and (type(row["tokens"]) is not int or row["tokens"] < 0):
                raise ValueError(f"Invalid token usage in reply event {row['event_id']}")
        return rows

    def submission_events(self, run_id: str) -> dict[str, int]:
        rows = self._db.query("""
            SELECT name, event_id FROM events WHERE process_id = %s AND
                ((category = %s AND name = %s) OR (category = %s AND name = %s))
        """, (run_id, Events.Configuration.CATEGORY, Events.Configuration.PROPOSAL_ACCEPTED,
               Events.SnakeLab.CATEGORY, Events.SnakeLab.SUBMITTED))
        return {row["name"]: row["event_id"] for row in rows}

    def choice_events(self, draft_id: str) -> list[dict]:
        """Read the setup trace without loading image snapshots or model output."""
        config, chat, llm, tool = Events.Configuration, Events.Conversation, Events.LLM, Events.Tool
        return self._db.query("""
            SELECT e.event_id, e.occurred_at, CURRENT_TIMESTAMP(6) AS observed_at,
                   e.parent_event_id, e.name, e.parameter,
                   CASE WHEN e.name = %s AND e.source_name = 'ConfigurationChoice'
                        THEN JSON_TYPE(JSON_EXTRACT(m.content, '$.content')) = 'ARRAY' END AS has_image,
                   CASE WHEN e.name IN (%s, %s, %s) THEN m.content
                        WHEN e.name = %s THEN JSON_EXTRACT(m.content, '$.usage')
                        WHEN e.name = %s THEN JSON_UNQUOTE(JSON_EXTRACT(m.content, '$.status'))
                   END AS detail
            FROM events e JOIN event_messages m USING (event_id)
            WHERE e.process_id = %s AND (
                (e.category = %s AND e.name IN (%s, %s)) OR
                (e.category = %s AND e.name IN (%s, %s, %s)) OR
                (e.category = %s AND e.name IN (%s, %s)) OR
                (e.category = %s AND e.name IN (%s, %s, %s)))
            ORDER BY e.event_id
        """, (chat.PROMPT, config.CHART_STARTED, config.CHART_FINISHED, tool.STARTED,
              chat.RESPONSE, tool.COMPLETED, draft_id,
              config.CATEGORY, config.CHART_STARTED, config.CHART_FINISHED,
              chat.CATEGORY, chat.PROMPT, chat.RESPONSE, chat.ENDED,
              llm.CATEGORY, llm.REQUEST_STARTED, llm.REQUEST_FAILED,
              tool.CATEGORY, tool.STARTED, tool.COMPLETED, tool.FAILED))
