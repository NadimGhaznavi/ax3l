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

    def latest_snakelab_proposal(self) -> dict[str, Any] | None:
        """Recover the latest accepted run and its recorded comparison, if any."""
        category = DEventCategory.Configuration
        rows = self._db.query("""
            SELECT p.process_id, c.event_id AS comparison_id, m.content AS comparison
            FROM events p
            LEFT JOIN events c ON c.event_id = (
                SELECT MAX(event_id) FROM events
                WHERE process_id = p.process_id AND category = %s AND name = %s
            )
            LEFT JOIN event_messages m ON m.event_id = c.event_id
            WHERE p.category = %s AND p.name = %s
              AND p.event_id > COALESCE((SELECT MAX(event_id) FROM events
                  WHERE category = %s AND name = %s), 0)
            ORDER BY p.event_id DESC LIMIT 1
        """, (category.CATEGORY, category.COMPARED, category.CATEGORY, category.PROPOSAL_ACCEPTED,
               category.CATEGORY, category.GOLDEN_SEED_INCREMENTED))
        return rows[0] if rows else None

    def stagnant_rounds(self) -> int:
        category = DEventCategory.Configuration
        return self._db.query("""
            SELECT COUNT(DISTINCT process_id) AS rounds FROM events
            WHERE category = %s AND name = %s AND event_id > COALESCE(
                (SELECT MAX(event_id) FROM events WHERE category = %s AND name = %s), 0)
        """, (category.CATEGORY, category.COMPARED,
               category.CATEGORY, category.GOLDEN_CREATED))[0]["rounds"]

    def pending_seed_rotation(self) -> dict[str, Any] | None:
        category = DEventCategory.Configuration
        rows = self._db.query("""
            SELECT i.event_id, m.content, s.event_id AS submitted_event_id, s.process_id AS run_id
            FROM events i JOIN event_messages m ON m.event_id = i.event_id
            LEFT JOIN events s ON s.parent_event_id = i.event_id AND s.name = %s AND s.category = %s
            WHERE i.name = %s AND i.category = %s
              AND NOT EXISTS (SELECT 1 FROM events g WHERE g.parent_event_id = s.event_id
                              AND g.name = %s AND g.category = %s)
            ORDER BY i.event_id DESC LIMIT 1
        """, (category.GOLDEN_SEED_INCREMENTED, category.CATEGORY,
               category.SEED_ROTATION_STARTED, category.CATEGORY,
               category.GOLDEN_CREATED, category.CATEGORY))
        return rows[0] if rows else None

    def latest_seed_baseline(self) -> str | None:
        category = DEventCategory.Configuration
        rows = self._db.query("""
            SELECT g.process_id FROM events g JOIN events s ON g.parent_event_id = s.event_id
            WHERE g.name = %s AND g.category = %s AND s.name = %s AND s.category = %s
            ORDER BY g.event_id DESC LIMIT 1
        """, (category.GOLDEN_CREATED, category.CATEGORY,
               category.GOLDEN_SEED_INCREMENTED, category.CATEGORY))
        return rows[0]["process_id"] if rows else None
