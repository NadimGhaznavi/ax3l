from typing import Any

from ax3l.app.DbMgr import DbMgr


class EventLogDb:
    def __init__(self, db: DbMgr):
        self._db = db

    def recent(self) -> list[dict[str, Any]]:
        """Return the latest 500 events, newest first."""
        rows = self._db.query("""
            SELECT e.event_id, e.occurred_at, e.name, e.category,
                   e.log_level, m.content
            FROM events e
            LEFT JOIN event_messages m USING (event_id)
            ORDER BY e.occurred_at DESC, e.event_id DESC
            LIMIT 500
        """)
        return rows
