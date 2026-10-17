"""Ax3l-owned reporting projections; source tables are read only."""

import json

from ax3l.app.DbMgr import DbMgr
from ax3l.app.snakelab.RoundRobinState import ROUND_ROBIN_ORDER
from ax3l.constants.DEventCategory import DEventCategory
from ax3l.constants.DSnakeLab import DSnakeLab


class ReportingDb:
    def __init__(self, db: DbMgr):
        self._db = db

    def initialize(self) -> None:
        """Explicitly create reporting tables, outside a transaction."""
        for sql in (
            """CREATE TABLE IF NOT EXISTS report_runs (
                summary_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                source_id BIGINT UNSIGNED NOT NULL UNIQUE,
                run_id CHAR(36) COLLATE utf8mb4_unicode_ci NOT NULL UNIQUE,
                games_played BIGINT UNSIGNED NOT NULL,
                moves_made BIGINT UNSIGNED NOT NULL,
                high_score INT UNSIGNED NULL,
                started_at DATETIME(6) NULL,
                completed_at DATETIME(6) NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS report_turns (
                completion_id BIGINT UNSIGNED PRIMARY KEY,
                process_id CHAR(36) NULL,
                parameter_index INT UNSIGNED NULL,
                INDEX idx_report_turn_process (process_id, completion_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS report_events (
                event_id BIGINT UNSIGNED PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                process_id CHAR(36) NULL,
                parameter_index INT UNSIGNED NULL,
                INDEX idx_report_event_name (name, event_id),
                INDEX idx_report_event_process (process_id, name, event_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS report_state (
                singleton TINYINT UNSIGNED PRIMARY KEY,
                games_played BIGINT UNSIGNED NOT NULL DEFAULT 0,
                moves_made BIGINT UNSIGNED NOT NULL DEFAULT 0,
                all_time_high_score INT UNSIGNED NULL,
                simulations_submitted BIGINT UNSIGNED NOT NULL DEFAULT 0,
                experiment_cycles BIGINT UNSIGNED NOT NULL DEFAULT 0,
                expected_parameter INT UNSIGNED NOT NULL DEFAULT 0,
                last_completion_id BIGINT UNSIGNED NOT NULL DEFAULT 0,
                refreshed_at DATETIME(6) NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        ):
            self._db.execute(sql)
        self._db.execute("INSERT IGNORE INTO report_state (singleton) VALUES (1)")

    def lock_state(self) -> dict:
        """Serialize refreshers; all projection writes share this transaction."""
        return self._db.query("SELECT * FROM report_state WHERE singleton = 1 FOR UPDATE")[0]

    def reset(self) -> None:
        """Rebuild only derived data, with the report state already locked."""
        self._db.execute("DELETE FROM report_runs")
        self._db.execute("DELETE FROM report_turns")
        self._db.execute("DELETE FROM report_events")
        self._db.execute("""UPDATE report_state SET games_played = 0, moves_made = 0,
            all_time_high_score = NULL, simulations_submitted = 0, experiment_cycles = 0,
            expected_parameter = 0, last_completion_id = 0, refreshed_at = NULL
            WHERE singleton = 1""")

    def last_summary_id(self) -> int:
        return self._db.query(
            "SELECT COALESCE(MAX(summary_id), 0) AS id FROM report_runs")[0]["id"]

    def pending_runs(self) -> list[dict]:
        """Recheck unfinished older IDs too; completion order need not match IDs."""
        return self._db.query(f"""
            SELECT s.run_id FROM `{DSnakeLab.DATABASE}`.simulation_runs s
            LEFT JOIN report_runs r ON r.run_id = s.run_id
            WHERE s.status = 'completed' AND r.summary_id IS NULL
            ORDER BY s.id LIMIT 256
        """)

    def summarize_runs(self, run_ids: list[str]) -> None:
        placeholders = ', '.join(['%s'] * len(run_ids))
        rows = self._db.query(f"""
            SELECT s.id AS source_id, s.run_id, COUNT(ep.episode) AS games_played,
                   COALESCE(SUM(ep.steps), 0) AS moves_made,
                   s.high_score, s.started_at, s.completed_at
            FROM `{DSnakeLab.DATABASE}`.simulation_runs s
            LEFT JOIN `{DSnakeLab.DATABASE}`.simulation_episodes ep ON ep.run_id = s.run_id
            WHERE s.run_id IN ({placeholders}) AND s.status = 'completed'
            GROUP BY s.id, s.run_id, s.high_score, s.started_at, s.completed_at
        """, run_ids)
        # Separate plain SELECTs from writes so an INSERT ... SELECT does not
        # take shared locks on SnakeLab's source rows during the initial extract.
        for row in rows:
            self._db.execute("""INSERT INTO report_runs
                (source_id, run_id, games_played, moves_made, high_score, started_at, completed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)""", tuple(row[key] for key in (
                    "source_id", "run_id", "games_played", "moves_made", "high_score",
                    "started_at", "completed_at")))

    def add_run_totals(self, after_summary_id: int) -> None:
        self._db.execute("""
            UPDATE report_state s CROSS JOIN (
                SELECT COALESCE(SUM(games_played), 0) AS games,
                       COALESCE(SUM(moves_made), 0) AS moves, MAX(high_score) AS score
                FROM report_runs WHERE summary_id > %s
            ) r
            SET s.games_played = s.games_played + r.games,
                s.moves_made = s.moves_made + r.moves,
                s.all_time_high_score = CASE
                    WHEN s.all_time_high_score IS NULL THEN r.score
                    WHEN r.score IS NULL THEN s.all_time_high_score
                    ELSE GREATEST(s.all_time_high_score, r.score) END
            WHERE s.singleton = 1
        """, (after_summary_id,))

    def last_event_id(self) -> int:
        return self._db.query(
            "SELECT COALESCE(MAX(event_id), 0) AS id FROM report_events")[0]["id"]

    def pending_events(self) -> list[dict]:
        """Find unseen IDs in one pass, revisiting late commits too."""
        category = DEventCategory.Configuration
        return self._db.query("""
            SELECT e.event_id FROM events e
            LEFT JOIN report_events r ON r.event_id = e.event_id
            WHERE e.category = %s AND e.name IN (%s, %s, %s, %s) AND r.event_id IS NULL
            ORDER BY e.event_id
        """, (category.CATEGORY, "round_robin_checkpoint", category.PROPOSAL_ACCEPTED,
               category.COMPARED, category.PARAMETER_SPACE_EXHAUSTED))

    def events(self, event_ids: list[int]) -> list[dict]:
        """Read checkpoint payloads only for a bounded batch of unseen events."""
        placeholders = ', '.join(['%s'] * len(event_ids))
        rows = self._db.query(f"""
            SELECT e.event_id, e.name, e.process_id,
                   CASE WHEN e.name = 'round_robin_checkpoint' THEN m.content END AS checkpoint
            FROM events e JOIN event_messages m USING (event_id)
            WHERE e.event_id IN ({placeholders}) ORDER BY e.event_id
        """, event_ids)
        for row in rows:
            content = row.pop("checkpoint")
            row["parameter_index"] = None
            if row["name"] != "round_robin_checkpoint":
                continue
            checkpoint = json.loads(content)
            if checkpoint["parameter_order"] != ROUND_ROBIN_ORDER:
                raise ValueError("Search parameter order changed; reset experiment events before resuming")
            index = checkpoint["index"]
            if type(index) is not int or not 0 <= index < len(ROUND_ROBIN_ORDER):
                raise ValueError("Invalid round-robin checkpoint index")
            row["parameter_index"] = index
        return rows

    def save_event(self, event: dict) -> None:
        self._db.execute("""INSERT INTO report_events (event_id, name, process_id, parameter_index)
            VALUES (%s, %s, %s, %s)""", (event["event_id"], event["name"],
                                           event["process_id"], event["parameter_index"]))

    def reset_turns(self) -> None:
        self._db.execute("DELETE FROM report_turns")

    def pending_turns(self, after_completion: int) -> list[dict]:
        """Resolve the existing round-count semantics entirely in reporting tables."""
        category = DEventCategory.Configuration
        rows = self._db.query("""
            SELECT c.event_id AS completion_id, c.name, c.process_id
            FROM report_events c
            LEFT JOIN report_turns t ON t.completion_id = c.event_id
            WHERE c.event_id > %s AND c.name IN (%s, %s)
              AND (t.completion_id IS NULL OR t.parameter_index IS NULL)
            ORDER BY c.event_id LIMIT 512
        """, (after_completion, category.COMPARED, category.PARAMETER_SPACE_EXHAUSTED))
        for row in rows:
            name = row.pop("name")
            row["parameter_index"] = None
            before = row["completion_id"]
            if name == category.COMPARED:
                proposals = self._db.query("""SELECT event_id FROM report_events
                    WHERE process_id = %s AND name = %s ORDER BY event_id LIMIT 1""",
                    (row["process_id"], category.PROPOSAL_ACCEPTED))
                if not proposals:
                    continue
                before = proposals[0]["event_id"]
            else:
                row["process_id"] = None
            checkpoints = self._db.query("""SELECT parameter_index FROM report_events
                WHERE name = 'round_robin_checkpoint' AND event_id < %s
                ORDER BY event_id DESC LIMIT 1""", (before,))
            if checkpoints:
                row["parameter_index"] = checkpoints[0]["parameter_index"]
        return rows

    def save_turn(self, turn: dict) -> None:
        self._db.execute("""INSERT INTO report_turns (completion_id, process_id, parameter_index)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE process_id = VALUES(process_id),
                                    parameter_index = VALUES(parameter_index)""",
            (turn["completion_id"], turn["process_id"], turn["parameter_index"]))

    def turns_after(self, completion_id: int) -> list[dict]:
        return self._db.query("""
            SELECT t.completion_id, t.parameter_index,
                   (t.parameter_index IS NOT NULL AND (t.process_id IS NULL OR NOT EXISTS (
                       SELECT 1 FROM report_turns previous
                       WHERE previous.process_id = t.process_id
                         AND previous.parameter_index IS NOT NULL
                         AND previous.completion_id < t.completion_id))) AS first_completion
            FROM report_turns t WHERE t.completion_id > %s ORDER BY t.completion_id
        """, (completion_id,))

    def save_progress(self, rounds: int, expected: int, last_completion: int) -> None:
        submitted = self._db.query(
            f"SELECT COUNT(*) AS n FROM `{DSnakeLab.DATABASE}`.simulation_runs")[0]["n"]
        self._db.execute("""
            UPDATE report_state SET experiment_cycles = %s, expected_parameter = %s,
                last_completion_id = %s, simulations_submitted = %s,
                refreshed_at = CURRENT_TIMESTAMP(6)
            WHERE singleton = 1
        """, (rounds, expected, last_completion, submitted))

    def totals(self) -> dict:
        row = self._db.query("""SELECT games_played, moves_made, all_time_high_score,
            simulations_submitted, experiment_cycles FROM report_state WHERE singleton = 1""")[0]
        return {key: int(value) if value is not None else None for key, value in row.items()}
