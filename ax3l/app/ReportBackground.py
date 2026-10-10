"""Schedule report animations and cache episode totals without blocking HTTP."""

from concurrent.futures import Future, ThreadPoolExecutor
import logging
from time import monotonic

import pymysql
import zmq

from ax3l.activity.SimulationAnimation import SimulationAnimation
from ax3l.app.DbMgr import DbMgr
from ax3l.app.EventLogDb import EventLogDb
from ax3l.constants.DReportMgr import DReportMgr
from ax3l.interface.SimulationGifStore import SimulationGifStore
from ax3l.interface.SnakeLab import SnakeLab


class ReportBackground:
    def __init__(self, gifs: SimulationGifStore, duration_ms: int):
        self._gifs = gifs
        self._duration_ms = duration_ms
        # A long game must not delay the independent totals query.
        self._animations = ThreadPoolExecutor(max_workers=1, thread_name_prefix="report-gif")
        self._totals = ThreadPoolExecutor(max_workers=1, thread_name_prefix="report-totals")
        self._status = ThreadPoolExecutor(max_workers=1, thread_name_prefix="report-status")
        self._gif_jobs: dict[str, Future] = {}
        self._gif_retry_after: dict[str, float] = {}
        self._totals_job: Future | None = None
        self._totals_value = {"games_played": None, "moves_made": None}
        self._totals_refresh_after = 0.0
        self._status_job: Future | None = None
        self._status_value = {"simulations_submitted": None, "experiment_cycles": None,
                              "all_time_high_score": None, "snake_lab_status": "Loading"}
        self._status_refresh_after = 0.0

    def animation_ready(self, run_id: str) -> bool:
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
            self._gif_jobs[run_id] = self._animations.submit(self._generate, run_id)
        return False

    def _generate(self, run_id: str) -> None:
        try:
            frames = SnakeLab().get_highscore_frames(run_id)
        except zmq.ZMQError:
            logging.exception("Unable to retrieve high-score frames for %s", run_id)
            return
        if frames is not None:
            self._gifs.save(run_id, SimulationAnimation.render(frames, self._duration_ms))

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
        return self._totals_value.copy()

    @staticmethod
    def _load_totals() -> dict[str, int] | None:
        try:
            return SnakeLab().get_episode_totals()
        except (pymysql.MySQLError, OSError):
            logging.exception("Unable to refresh report episode totals")
            return None

    def status(self) -> dict:
        """Cache the remaining homepage counts and control-service status."""
        if self._status_job is not None and self._status_job.done():
            value = self._status_job.result()
            if value is not None:
                self._status_value = value
            self._status_job = None
            self._status_refresh_after = monotonic() + DReportMgr.BACKGROUND_REFRESH_SECONDS
        if self._status_job is None and monotonic() >= self._status_refresh_after:
            self._status_job = self._status.submit(self._load_status)
        return self._status_value.copy()

    @staticmethod
    def _load_status() -> dict | None:
        try:
            snake = SnakeLab()
            try:
                running = snake.is_simulation_running()
            except zmq.ZMQError:
                status = "Service Unavailable"
            else:
                status = "Running Simulation" if running else "Idle"
            started = monotonic()
            db = DbMgr(initialize_event_tables=False)
            try:
                cycles = EventLogDb(db).experiment_cycles()
            finally:
                db.close()
            elapsed = monotonic() - started
            if elapsed >= 1:
                logging.warning("Report completed-experiments query took %.3f seconds", elapsed)
            return {"snake_lab_status": status, "experiment_cycles": cycles,
                    "simulations_submitted": snake.get_num_sims(),
                    "all_time_high_score": snake.get_high_score()}
        except (pymysql.MySQLError, OSError):
            logging.exception("Unable to refresh report status")
            return None

    def close(self) -> None:
        self._animations.shutdown(wait=True, cancel_futures=True)
        self._totals.shutdown(wait=True, cancel_futures=True)
        self._status.shutdown(wait=True, cancel_futures=True)
