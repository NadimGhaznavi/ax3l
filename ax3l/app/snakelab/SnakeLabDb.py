"""Read Snake Lab simulation data through AX3L's database manager."""

import json

from ax3l.app.DbMgr import DbMgr


class SnakeLabDb:
    def __init__(self, db: DbMgr):
        self._db = db

    def get_num_sims(self) -> int:
        """Count all stored runs, including repeated configurations and all statuses."""
        return self._db.query("SELECT COUNT(*) AS num_sims FROM simulation_runs")[0]["num_sims"]

    def get_config(self, run_id: str) -> dict | None:
        rows = self._db.query(
            "SELECT config FROM simulation_runs WHERE run_id = %s", (run_id,)
        )
        return json.loads(rows[0]["config"]) if rows else None

    def is_config_unique(self, config: dict) -> bool:
        """Compare the full config across all runs, independent of JSON key order."""
        rows = self._db.query(
            "SELECT 1 FROM simulation_runs WHERE JSON_EQUALS(config, %s) LIMIT 1",
            (json.dumps(config, allow_nan=False),),
        )
        return not rows

    def get_episode_losses(self, run_id: str) -> list[tuple[int, float | None]]:
        """Read losses in episode order, preserving episodes with no training loss."""
        rows = self._db.query(
            "SELECT episode, loss FROM simulation_episodes WHERE run_id = %s ORDER BY episode",
            (run_id,),
        )
        return [(row["episode"], row["loss"]) for row in rows]
