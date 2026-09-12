"""Read Snake Lab simulation data through AX3L's database manager."""

from ax3l.app.DbMgr import DbMgr


class SnakeLabDb:
    def __init__(self, db: DbMgr):
        self._db = db

    def get_num_sims(self) -> int:
        """Count all stored runs, including repeated configurations and all statuses."""
        return self._db.query("SELECT COUNT(*) AS num_sims FROM simulation_runs")[0]["num_sims"]
