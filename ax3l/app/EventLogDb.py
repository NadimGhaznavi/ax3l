from typing import Any

from ax3l.app.DbMgr import DbMgr
from ax3l.constants.DEventCategory import DEventCategory


class EventLogDb:
    def __init__(self, db: DbMgr):
        self._db = db

    def recent(self) -> list[dict[str, Any]]:
        """Return the latest 500 events, newest first."""
        rows = self._db.query("""
            SELECT e.event_id, e.occurred_at, e.name, e.category,
                   e.log_level, e.process_id, m.content
            FROM events e
            LEFT JOIN event_messages m USING (event_id)
            ORDER BY e.occurred_at DESC, e.event_id DESC
            LIMIT 500
        """)
        return rows

    def get(self, event_id: int) -> dict[str, Any] | None:
        rows = self._db.query("""
            SELECT e.*, m.content
            FROM events e LEFT JOIN event_messages m USING (event_id)
            WHERE e.event_id = %s
        """, (event_id,))
        return rows[0] if rows else None

    def current_golden_config(self) -> dict[str, Any] | None:
        """Return the latest golden creation's run reference and reason."""
        category = DEventCategory.Configuration
        rows = self._db.query("""
            SELECT e.process_id, m.content AS reason
            FROM events e JOIN event_messages m USING (event_id)
            WHERE e.category = %s AND e.name = %s
            ORDER BY e.occurred_at DESC, e.event_id DESC
            LIMIT 1
        """, (category.CATEGORY, category.GOLDEN_CREATED))
        return rows[0] if rows else None
