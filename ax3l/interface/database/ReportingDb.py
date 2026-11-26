"""Own the incremental run summaries and current reporting counters."""

from ax3l.interface.database.DbMgr import DbMgr
from ax3l.interface.database.EventLogDb import EventLogDb
from ax3l.constants.DSnakeLab import DSnakeLab


class ReportingDb:
    def __init__(self, db: DbMgr):
        self._db = db

    def initialize(self) -> None:
        """Create only Ax3l's derived reporting tables, outside transactions."""
        self._db.execute("""CREATE TABLE IF NOT EXISTS report_runs (
            summary_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            source_id BIGINT UNSIGNED NOT NULL UNIQUE,
            run_id CHAR(36) COLLATE utf8mb4_unicode_ci NOT NULL UNIQUE,
            games_played BIGINT UNSIGNED NOT NULL,
            moves_made BIGINT UNSIGNED NOT NULL,
            high_score INT UNSIGNED NULL,
            started_at DATETIME(6) NULL,
            completed_at DATETIME(6) NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
        self._db.execute("""CREATE TABLE IF NOT EXISTS report_state (
            singleton TINYINT UNSIGNED PRIMARY KEY,
            games_played BIGINT UNSIGNED NOT NULL DEFAULT 0,
            moves_made BIGINT UNSIGNED NOT NULL DEFAULT 0,
            all_time_high_score INT UNSIGNED NULL,
            simulations_submitted BIGINT UNSIGNED NOT NULL DEFAULT 0,
            experiment_cycles BIGINT UNSIGNED NOT NULL DEFAULT 0,
            refreshed_at DATETIME(6) NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
        self._db.execute("INSERT IGNORE INTO report_state (singleton) VALUES (1)")

    def reset(self) -> None:
        self._db.execute("DELETE FROM report_runs")
        self._db.execute("""UPDATE report_state SET games_played = 0, moves_made = 0,
            all_time_high_score = NULL, simulations_submitted = 0, experiment_cycles = 0,
            refreshed_at = NULL WHERE singleton = 1""")

    def save_progress(self) -> None:
        submitted = self._db.query(
            f"SELECT COUNT(*) AS n FROM `{DSnakeLab.DATABASE}`.simulation_runs")[0]["n"]
        cycles = EventLogDb(self._db).experiment_cycles()
        self._db.execute("""UPDATE report_state SET experiment_cycles = %s,
            simulations_submitted = %s, refreshed_at = CURRENT_TIMESTAMP(6)
            WHERE singleton = 1""", (cycles, submitted))

    def lock_state(self) -> dict:
        """Serialize refreshers; all projection writes share this transaction."""
        return self._db.query("SELECT * FROM report_state WHERE singleton = 1 FOR UPDATE")[0]

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

    def totals(self) -> dict:
        row = self._db.query("""SELECT games_played, moves_made, all_time_high_score,
            simulations_submitted, experiment_cycles FROM report_state WHERE singleton = 1""")[0]
        return {key: int(value) if value is not None else None for key, value in row.items()}
