"""Refresh derived reports atomically, without modifying SnakeLab source data."""

from ax3l.interface.database.DbMgr import DbMgr
from ax3l.interface.database.ReportingDb import ReportingDb


class ReportingRefresh:
    def __init__(self, db: DbMgr):
        self._db = db
        self._reports = ReportingDb(db)

    def refresh(self, *, initialize: bool = False, rebuild: bool = False) -> dict:
        if initialize:
            self._reports.initialize()
        with self._db.transaction():
            self._reports.lock_state()
            if rebuild:
                self._reports.reset()
            last_summary = self._reports.last_summary_id()
            while runs := self._reports.pending_runs():
                self._reports.summarize_runs([run["run_id"] for run in runs])
            self._reports.add_run_totals(last_summary)
            self._reports.save_progress()
            return self._reports.totals()
