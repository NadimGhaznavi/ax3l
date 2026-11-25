from typing import Any

from ax3l.interface.database.DbMgr import DbMgr
from ax3l.constants.DEventCategory import DEventCategory
from ax3l.constants.DSnakeLab import DSnakeLab


class EventLogDb:
    def __init__(self, db: DbMgr):
        self._db = db

    def log(
        self,
        name: str,
        category: str,
        log_level: str,
        content: str,
        *,
        process_id: str | None = None,
        parent_event_id: int | None = None,
        source_name: str | None = None,
        parameter: str | None = None,
        ax3l_version: str | None = None,
        experiment_score: dict | None = None,
    ) -> int:
        """Commit an event and its message together and return the event ID.

        This method owns its transaction; call it outside transaction().
        """
        with self._db.transaction():
            self._db.execute(
                """INSERT INTO events
                   (name, category, log_level, process_id, parent_event_id, source_name, parameter, ax3l_version)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (name, category, log_level, process_id, parent_event_id, source_name, parameter, ax3l_version),
            )
            event_id = self._db.query("SELECT LAST_INSERT_ID() AS event_id")[0]["event_id"]
            self._db.execute(
                "INSERT INTO event_messages (event_id, content) VALUES (%s, %s)",
                (event_id, content),
            )
            if experiment_score is not None:
                self._db.execute(
                    "INSERT INTO experiment_highscores (event_id, simulations, score, seed) VALUES (%s, %s, %s, %s)",
                    (event_id, experiment_score["simulations"], experiment_score["score"], experiment_score["seed"]),
                )
        return event_id


    def recent(self) -> list[dict[str, Any]]:
        """Return the latest 500 events, newest first."""
        rows = self._db.query(f"""
            WITH recent_events AS (
                SELECT event_id, occurred_at, name, category, log_level,
                       process_id, source_name, parameter, ax3l_version
                FROM events
                ORDER BY occurred_at DESC, event_id DESC
                LIMIT 500
            )
            SELECT e.event_id, e.occurred_at, e.name, e.category,
                   e.log_level, e.process_id, e.source_name, e.parameter, e.ax3l_version, m.content,
                   r.high_score AS simulation_high_score
            FROM recent_events e
            LEFT JOIN event_messages m USING (event_id)
            LEFT JOIN `{DSnakeLab.DATABASE}`.simulation_runs r
                ON r.run_id = e.process_id COLLATE utf8mb4_unicode_ci
                AND e.category = 'SnakeLab' AND e.name = 'simulation_completed'
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

    def golden_configurations(self) -> list[dict[str, Any]]:
        """Link promotions to the draft's final parameter reply."""
        return self._db.query("""
            WITH proposals AS (
                SELECT e.event_id, e.process_id AS run_id,
                       JSON_UNQUOTE(JSON_EXTRACT(m.content, '$.draft_id')) AS draft_id
                FROM events e JOIN event_messages m USING (event_id)
                WHERE e.category = 'Configuration' AND e.name = 'proposal_accepted'
            )
            SELECT g.event_id, g.occurred_at, g.process_id,
                   h.score AS high_score, r.event_id AS reply_id,
                   rm.content AS response, gm.content AS decision
            FROM events g
            LEFT JOIN event_messages gm ON gm.event_id = g.event_id
            LEFT JOIN experiment_highscores h ON h.event_id = g.event_id
            LEFT JOIN proposals t ON t.event_id = (
                SELECT MIN(event_id) FROM proposals WHERE run_id = g.process_id)
            LEFT JOIN events r ON r.event_id = (
                SELECT MAX(event_id) FROM events
                WHERE process_id = t.draft_id AND event_id < t.event_id
                  AND category = 'Conversation' AND name = 'reply_received')
            LEFT JOIN event_messages rm ON rm.event_id = r.event_id
            WHERE g.category = %s AND g.name = %s
            ORDER BY g.occurred_at DESC, g.event_id DESC
        """, (DEventCategory.Configuration.CATEGORY, DEventCategory.Configuration.GOLDEN_CREATED))


    def experiment_cycles(self) -> int:
        """Count compared complete configurations across seeds."""
        category = DEventCategory.Configuration
        return self._db.query("""
            SELECT COUNT(DISTINCT process_id) AS rounds FROM events
            WHERE category = %s AND name = %s
        """, (category.CATEGORY, category.COMPARED))[0]["rounds"]

    def experiment_highscores(self) -> list[dict[str, Any]]:
        """Read golden scores and completed same-seed ties in decision order."""
        return self._db.query(f"""
            WITH runs AS (
                SELECT run_id, status, high_score,
                       ROW_NUMBER() OVER (ORDER BY id) AS simulations
                FROM `{DSnakeLab.DATABASE}`.simulation_runs
            ), history AS (
                SELECT h.event_id, h.simulations, h.score, h.seed, e.process_id AS run_id,
                       m.content AS reason, 0 AS matched
                FROM experiment_highscores h JOIN events e USING (event_id)
                JOIN event_messages m USING (event_id)
                UNION ALL
                SELECT e.event_id, r.simulations, r.high_score, c.seed, e.process_id,
                       JSON_UNQUOTE(JSON_EXTRACT(m.content, '$.reason')), 1
                FROM events e JOIN event_messages m USING (event_id)
                JOIN runs r ON r.run_id = e.process_id COLLATE utf8mb4_unicode_ci
                JOIN `{DSnakeLab.DATABASE}`.configurations c ON c.run_id = r.run_id
                JOIN experiment_highscores h ON h.event_id = (
                    SELECT MAX(event_id) FROM experiment_highscores WHERE event_id < e.event_id)
                WHERE e.category = 'Configuration' AND e.name = 'configuration_compared'
                  AND r.status = 'completed' AND r.high_score = h.score AND c.seed = h.seed
            )
            SELECT simulations, score, seed, run_id, reason, matched
            FROM history ORDER BY event_id
        """)

    def simulation_metrics(self) -> list[dict[str, Any]]:
        """Include every draft conversation and the run's vision analysis time."""
        return self._db.query(f"""
            WITH proposals AS (
                SELECT e.event_id, e.process_id AS run_id,
                       JSON_UNQUOTE(JSON_EXTRACT(m.content, '$.draft_id')) AS draft_id
                FROM events e JOIN event_messages m USING (event_id)
                WHERE e.category = 'Configuration' AND e.name = 'proposal_accepted'
            ), requests AS (
                SELECT r.event_id, r.process_id,
                       TIMESTAMPDIFF(MICROSECOND, p.occurred_at, r.occurred_at) / 1000000.0 AS seconds
                FROM events r
                LEFT JOIN events p ON p.event_id = (
                    SELECT MAX(event_id) FROM events
                    WHERE parent_event_id = r.parent_event_id AND event_id < r.event_id
                      AND category = 'Conversation' AND name IN ('prompt_sent', 'reply_received'))
                    AND p.name = 'prompt_sent'
                WHERE r.category = 'Conversation' AND r.name = 'reply_received'
            )
            SELECT s.run_id, s.high_score,
                   ep.total_steps, ep.total_steps / NULLIF(ep.episodes, 0) AS steps_per_episode,
                   TIMESTAMPDIFF(MICROSECOND, s.started_at, s.completed_at) / 1000000.0 AS runtime_seconds,
                   CASE WHEN COUNT(q.event_id) = 0 THEN 0
                        WHEN COUNT(q.seconds) < COUNT(q.event_id) THEN NULL
                        ELSE SUM(q.seconds) END AS llm_seconds
            FROM `{DSnakeLab.DATABASE}`.simulation_runs s
            LEFT JOIN (
                SELECT run_id, SUM(steps) AS total_steps, COUNT(*) AS episodes
                FROM `{DSnakeLab.DATABASE}`.simulation_episodes GROUP BY run_id
            ) ep ON ep.run_id = s.run_id
            LEFT JOIN proposals t ON t.event_id = (
                SELECT MIN(event_id) FROM proposals
                WHERE run_id COLLATE utf8mb4_unicode_ci = s.run_id)
            LEFT JOIN requests q ON (q.process_id = t.draft_id AND q.event_id < t.event_id)
                OR q.process_id COLLATE utf8mb4_unicode_ci = s.run_id
            WHERE s.status = 'completed'
            GROUP BY s.id, s.run_id, s.started_at, s.completed_at, s.high_score, ep.total_steps, ep.episodes
            ORDER BY s.id
        """)
