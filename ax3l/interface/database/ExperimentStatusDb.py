"""Read selection and evaluation conversations for the active single-view experiment."""

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
        views = tuple(VIEWS)
        placeholders = ", ".join(["%s"] * len(views))
        events = self._db.query(f"""
            SELECT e.event_id, e.occurred_at, CURRENT_TIMESTAMP(6) AS observed_at,
                   e.name, e.category, e.log_level, e.source_name,
                   e.process_id, e.parent_event_id, e.parameter,
                   CASE WHEN e.category = %s AND e.name = %s THEN NULL ELSE m.content END AS content
            FROM events e JOIN event_messages m USING (event_id)
            WHERE e.process_id = %s AND e.parameter IN ({placeholders})
            ORDER BY e.event_id
        """, (Events.Conversation.CATEGORY, Events.Conversation.PROMPT, state.experiment_id, *views))
        return dict(state=state, events=events, evaluation_id=state.experiment_id,
                    selection_config=experiments.initial_config(state.experiment_id))
