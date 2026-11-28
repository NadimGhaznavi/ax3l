"""Read Snake Lab simulation data through AX3L's database manager."""

from ax3l.interface.SimulationConfiguration import SCHEMA
from ax3l.interface.database.DbMgr import DbMgr


def _configuration_fields(node, path=()):
    for name, field in node["properties"].items():
        parts = path + (name,)
        if field["type"] == "object":
            yield from _configuration_fields(field, parts)
        else:
            yield "_".join(parts), parts, field["type"]


CONFIGURATION_FIELDS = tuple(_configuration_fields(SCHEMA))
CONFIGURATION_COLUMNS = ", ".join(column for column, _, _ in CONFIGURATION_FIELDS)


def _config_from_row(row):
    config = {}
    for column, path, kind in CONFIGURATION_FIELDS:
        target = config
        for part in path[:-1]:
            target = target.setdefault(part, {})
        target[path[-1]] = {"integer": int, "number": float, "string": str}[kind](row[column])
    return config


def _config_values(config):
    values = []
    for _, path, _ in CONFIGURATION_FIELDS:
        value = config
        for part in path:
            value = value[part]
        values.append(value)
    return tuple(values)


class SnakeLabDb:
    def __init__(self, db: DbMgr):
        self._db = db



    def get_num_sims(self) -> int:
        """Count all stored runs, including repeated configurations and all statuses."""
        return self._db.query("SELECT COUNT(*) AS num_sims FROM simulation_runs")[0]["num_sims"]

    def get_episode_totals(self) -> dict[str, int]:
        """Return games played and moves made across all stored episodes."""
        row = self._db.query(
            "SELECT COUNT(*) AS games_played, COALESCE(SUM(steps), 0) AS moves_made "
            "FROM simulation_episodes"
        )[0]
        return {"games_played": int(row["games_played"]),
                "moves_made": int(row["moves_made"])}

    def get_high_score(self) -> int | None:
        """Return the highest recorded score across all runs, or None before any score."""
        return self._db.query(
            "SELECT MAX(high_score) AS high_score FROM simulation_runs"
        )[0]["high_score"]

    def get_run_scores(self) -> dict[int, int | None]:
        """Return every simulation ID and latest score, including unscored runs."""
        return {row["id"]: row["high_score"] for row in self._db.query(
            "SELECT id, high_score FROM simulation_runs ORDER BY id"
        )}

    def get_episode_scores(self, run_id: str) -> list[dict]:
        """Return one run's training scores in epoch order."""
        return self._db.query(
            "SELECT episode, score FROM simulation_episodes WHERE run_id = %s ORDER BY episode",
            (run_id,),
        )

    def get_exploration_episodes(self, run_id: str) -> list[dict]:
        """Return recorded epsilon values and scores for the exploration chart."""
        return self._db.query(
            "SELECT episode, score, epsilon "
            "FROM simulation_episodes WHERE run_id = %s ORDER BY episode", (run_id,),
        )

    def get_reward_episodes(self, run_id: str) -> list[dict]:
        """Return scores, move counts, and terminal outcomes for reward comparisons."""
        return self._db.query(
            "SELECT episode, score, steps, outcome FROM simulation_episodes "
            "WHERE run_id = %s ORDER BY episode", (run_id,),
        )

    def get_training_episodes(self, run_id: str) -> list[dict]:
        """Return recorded scores and nullable episode losses for training comparisons."""
        return self._db.query(
            "SELECT episode, score, loss FROM simulation_episodes "
            "WHERE run_id = %s ORDER BY episode", (run_id,),
        )

    def get_config(self, run_id: str) -> dict | None:
        rows = self._db.query(
            f"SELECT {CONFIGURATION_COLUMNS} FROM configurations WHERE run_id = %s", (run_id,)
        )
        return _config_from_row(rows[0]) if rows else None


    def get_run_summary(self, run_id: str) -> dict | None:
        rows = self._db.query(
            "SELECT id, run_id, project_version, high_score, completed_at, high_score_snapshot "
            "FROM simulation_runs WHERE run_id = %s", (run_id,),
        )
        return rows[0] if rows else None

    def get_run_result(self, run_id: str) -> dict | None:
        rows = self._db.query(
            "SELECT r.run_id, r.status, r.high_score, c.* FROM simulation_runs r "
            "JOIN configurations c ON c.run_id = r.run_id WHERE r.run_id = %s",
            (run_id,),
        )
        if not rows:
            return None
        row = rows[0]
        return {**{key: row[key] for key in ("run_id", "status", "high_score")},
                "config": _config_from_row(row)}




    def get_latest_completed_run_id(self) -> str | None:
        rows = self._db.query("""
            SELECT run_id FROM simulation_runs
            WHERE status = 'completed' AND high_score IS NOT NULL
            ORDER BY completed_at DESC, id DESC LIMIT 1
        """)
        return rows[0]["run_id"] if rows else None

    def get_all_time_best_run_id(self) -> str | None:
        """Use the earliest completed record to resolve tied all-time scores."""
        rows = self._db.query("""
            SELECT run_id FROM simulation_runs
            WHERE status = 'completed' AND high_score IS NOT NULL
            ORDER BY high_score DESC, id LIMIT 1
        """)
        return rows[0]["run_id"] if rows else None

    def find_config_run(self, config: dict) -> str | None:
        conditions = " AND ".join(f"c.{column} = %s" for column, _, _ in CONFIGURATION_FIELDS)
        rows = self._db.query(
            "SELECT r.run_id FROM simulation_runs r JOIN configurations c ON c.run_id = r.run_id "
            f"WHERE {conditions} ORDER BY r.id DESC LIMIT 1", _config_values(config)
        )
        return rows[0]["run_id"] if rows else None






    def get_episode_diagnostics(self, run_id: str) -> dict:
        row = self._db.query("""
            SELECT COUNT(*) AS episodes,
                   COALESCE(SUM(epsilon_injections), 0) AS epsilon_injections,
                   COALESCE(SUM(epsilon_nice_injections), 0) AS epsilon_nice_injections,
                   COALESCE(SUM(epsilon = 0), 0) AS post_epsilon_episodes,
                   SUM(reward) AS total_reward,
                   COALESCE(SUM(outcome = 'wall'), 0) AS wall,
                   COALESCE(SUM(outcome = 'snake'), 0) AS snake,
                   COALESCE(SUM(outcome = 'max_moves'), 0) AS max_moves,
                   COALESCE(SUM(outcome = 'board_filled'), 0) AS board_filled
            FROM simulation_episodes WHERE run_id = %s
        """, (run_id,))[0]
        return {key: (None if value is None else float(value)) if key == "total_reward"
                else int(value) for key, value in row.items()}

