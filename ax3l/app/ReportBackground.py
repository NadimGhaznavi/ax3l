"""Refresh persistent reporting summaries and animations without blocking HTTP."""

from concurrent.futures import Future, ThreadPoolExecutor
import logging
from time import monotonic

import pymysql
import zmq

from ax3l.activity.SimulationAnimation import SimulationAnimation
from ax3l.app.DbMgr import DbMgr
from ax3l.app.ReportingRefresh import ReportingRefresh
from ax3l.constants.DReportMgr import DReportMgr
from ax3l.interface.SimulationGifStore import SimulationGifStore
from ax3l.interface.SnakeLab import SnakeLab


class ReportBackground:
    def __init__(self, gifs: SimulationGifStore, duration_ms: int):
        self._gifs = gifs
        self._duration_ms = duration_ms
        # A long game or control-service outage must not delay reporting refreshes.
        self._animations = ThreadPoolExecutor(max_workers=1, thread_name_prefix="report-gif")
        self._totals = ThreadPoolExecutor(max_workers=1, thread_name_prefix="report-totals")
        self._status = ThreadPoolExecutor(max_workers=1, thread_name_prefix="report-status")
        self._gif_jobs: dict[str, Future] = {}
        self._gif_retry_after: dict[str, float] = {}
        self._totals_job: Future | None = None
        self._totals_value = {"games_played": None, "moves_made": None,
                              "simulations_submitted": None, "experiment_cycles": None,
                              "all_time_high_score": None}
        self._reporting_initialized = False
        self._totals_refresh_after = 0.0
        self._status_job: Future | None = None
        self._status_value = {"snake_lab_status": "Loading"}
        self._status_refresh_after = 0.0

    def animation_ready(self, run_id: str, simulation_id: int) -> bool:
        """Return immediately; schedule one job per missing animation."""
        job = self._gif_jobs.get(run_id)
        if job is not None and job.done():
            job.result()  # Unexpected worker failures remain visible to the caller.
            del self._gif_jobs[run_id]
            self._gif_retry_after[run_id] = monotonic() + DReportMgr.BACKGROUND_REFRESH_SECONDS
        if self._gifs.path(run_id).is_file():
            self._gif_retry_after.pop(run_id, None)
            return True
        if (run_id not in self._gif_jobs
                and monotonic() >= self._gif_retry_after.get(run_id, 0)):
            self._gif_jobs[run_id] = self._animations.submit(self._generate, run_id, simulation_id)
        return False

    def _generate(self, run_id: str, simulation_id: int) -> None:
        try:
            frames = SnakeLab().get_highscore_frames(run_id)
        except zmq.ZMQError:
            logging.exception("Unable to retrieve high-score frames for %s", run_id)
            return
        if frames is not None:
            self._gifs.save(run_id, SimulationAnimation.render(frames, self._duration_ms,
                                                             simulation_id=simulation_id))

    def episode_totals(self) -> dict[str, int | None]:
        """Serve the last completed result while refreshing a stale cache."""
        if self._totals_job is not None and self._totals_job.done():
            value = self._totals_job.result()
            if value is not None:
                self._totals_value = value
            self._totals_job = None
            self._totals_refresh_after = monotonic() + DReportMgr.BACKGROUND_REFRESH_SECONDS
        if self._totals_job is None and monotonic() >= self._totals_refresh_after:
            self._totals_job = self._totals.submit(self._load_totals)
        return {key: self._totals_value[key] for key in ("games_played", "moves_made")}

    def _load_totals(self) -> dict[str, int | None] | None:
        try:
            db = DbMgr(initialize_event_tables=False)
            try:
                totals = ReportingRefresh(db).refresh(initialize=not self._reporting_initialized)
                self._reporting_initialized = True
                return totals
            finally:
                db.close()
        except (pymysql.MySQLError, OSError):
            logging.exception("Unable to refresh reporting summaries")
            return None

    def status(self) -> dict:
        """Serve reporting counters and independent control-service status."""
        self.episode_totals()
        if self._status_job is not None and self._status_job.done():
            value = self._status_job.result()
            if value is not None:
                self._status_value = value
            self._status_job = None
            self._status_refresh_after = monotonic() + DReportMgr.BACKGROUND_REFRESH_SECONDS
        if self._status_job is None and monotonic() >= self._status_refresh_after:
            self._status_job = self._status.submit(self._load_status)
        return {**{key: self._totals_value[key] for key in (
                    "simulations_submitted", "experiment_cycles", "all_time_high_score")},
                **self._status_value}

    @staticmethod
    def _load_status() -> dict | None:
        try:
            running = SnakeLab().is_simulation_running()
        except zmq.ZMQError:
            status = "Service Unavailable"
        else:
            status = "Running Simulation" if running else "Idle"
        return {"snake_lab_status": status}

    def close(self) -> None:
        self._animations.shutdown(wait=True, cancel_futures=True)
        self._totals.shutdown(wait=True, cancel_futures=True)
        self._status.shutdown(wait=True, cancel_futures=True)
