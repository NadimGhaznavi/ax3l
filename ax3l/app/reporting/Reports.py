"""Read report data through the application interfaces."""

from contextlib import contextmanager
from threading import Lock
from uuid import UUID

from ax3l.app.reporting.ReportBackground import ReportBackground
from ax3l.interface.database.DbMgr import DbMgr
from ax3l.interface.database.EventLogDb import EventLogDb
from ax3l.interface.database.ExperimentStatusDb import ExperimentStatusDb
from ax3l.interface.SimulationGifStore import SimulationGifStore
from ax3l.interface.SnakeLab import SnakeLab


class Reports:
    def __init__(self, snake: SnakeLab, background: ReportBackground, gifs: SimulationGifStore):
        self._snake = snake
        self._background = background
        self._gifs = gifs
        self._background_lock = Lock()

    @contextmanager
    def _database(self):
        db = DbMgr(initialize_event_tables=False)
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def _events(self):
        with self._database() as db:
            yield EventLogDb(db)

    def animation_url(self, run_id: str, simulation_id: int) -> str | None:
        with self._background_lock:
            if not self._background.animation_ready(run_id, simulation_id):
                return None
        return f"/simulation-gifs/{self._gifs.directory.name}/{UUID(run_id)}.gif"

    def recent(self) -> dict:
        with self._database() as db:
            log = EventLogDb(db)
            events = log.recent()
            golden = log.current_golden_config()
            experiment = ExperimentStatusDb(db).read()
        state = experiment["state"]
        runs = {run_id: self._snake.get_run_result(run_id)
                for run_id in dict.fromkeys((state.reference_run_id, state.run_id))
                if run_id} if state else {}
        reference = runs.get(state.reference_run_id) if state else None
        candidate = runs.get(state.run_id) if state else None
        experiment.update(reference_run=reference, candidate_run=candidate,
                          reference_config=reference["config"] if reference else None,
                          latest_config=candidate["config"] if candidate else None)
        current = self._snake.get_run_summary(golden["process_id"]) if golden else None
        score = current["high_score"] if current else None
        with self._background_lock:
            totals = {**self._background.status(), **self._background.episode_totals()}
        totals["all_time_high_score"] = max(
            (value for value in (totals["all_time_high_score"], score) if value is not None),
            default=None,
        )
        return dict(events=events, experiment=experiment, high_score=score, current_run=current,
                    current_board_gif_url=self.animation_url(golden["process_id"], current["id"])
                    if current else None, **totals)

    def event(self, event_id: int) -> dict | None:
        with self._events() as log:
            return log.get(event_id)

    def golden_configurations(self) -> list[dict]:
        with self._events() as log:
            return log.golden_configurations()

    def simulation_metrics(self) -> list[dict]:
        with self._events() as log:
            return log.simulation_metrics()

    def experiment_highscores(self) -> dict:
        with self._events() as log:
            history = log.experiment_highscores()
        return dict(history=history, submitted=self._snake.get_num_sims())

    def score_distribution(self) -> dict[int, int | None]:
        return self._snake.get_run_scores()

    def simulation(self, run_id: str) -> dict | None:
        run = self._snake.get_run_summary(run_id)
        if run is None:
            return None
        return dict(run=run, board_gif_url=self.animation_url(run_id, run["id"]),
                    config=self._snake.get_config(run_id),
                    diagnostics=self._snake.get_episode_diagnostics(run_id))

    def configuration(self, run_id: str) -> dict | None:
        return self._snake.get_config(run_id)
