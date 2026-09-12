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
