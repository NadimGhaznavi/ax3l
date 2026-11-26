"""Read the current selection pass and its preceding result evaluations."""

from ax3l.constants.DEventCategory import DEventCategory as Events
from ax3l.entities.ExperimentView import VIEWS
from ax3l.interface.database.DbMgr import DbMgr
from ax3l.interface.database.ExperimentDb import ExperimentDb


class ExperimentStatusDb:
    def __init__(self, db: DbMgr):
        self._db = db

    def read(self) -> dict:
        experiments = ExperimentDb(self._db)
        state = experiments.load()
        if state is None:
            return dict(state=None, events=[], selection_config=None, evaluation_id=None)

        evaluation_id = state.experiment_id if state.phase in ("evaluating", "completed") else None
        views = tuple(VIEWS)
        placeholders = ", ".join(["%s"] * len(views))
        if evaluation_id is None:
            # Evaluations include an image; selection prompts are text-only.
            rows = self._db.query(f"""
                SELECT e.process_id FROM events e JOIN event_messages m USING (event_id)
                WHERE e.category = %s AND e.name = %s AND e.parameter IN ({placeholders})
                  AND JSON_TYPE(JSON_EXTRACT(m.content, '$.content')) = 'ARRAY'
                ORDER BY e.event_id DESC LIMIT 1
            """, (Events.Conversation.CATEGORY, Events.Conversation.PROMPT, *views))
            evaluation_id = rows[0]["process_id"] if rows else None

        events = self._db.query(f"""
            SELECT e.event_id, e.occurred_at, e.name, e.category, e.log_level,
                   e.process_id, e.parent_event_id, e.parameter,
                   CASE WHEN e.category = %s AND e.name = %s
                        THEN JSON_TYPE(JSON_EXTRACT(m.content, '$.content')) END AS prompt_type,
                   CASE WHEN e.category = %s AND e.name = %s THEN NULL ELSE m.content END AS content
            FROM events e JOIN event_messages m USING (event_id)
            WHERE e.process_id IN (%s, %s) AND e.parameter IN ({placeholders})
            ORDER BY e.event_id
        """, (Events.Conversation.CATEGORY, Events.Conversation.PROMPT,
              Events.Conversation.CATEGORY, Events.Conversation.PROMPT,
              state.experiment_id, evaluation_id, *views))
        return dict(state=state, events=events, evaluation_id=evaluation_id,
                    selection_config=experiments.initial_config(state.experiment_id))
