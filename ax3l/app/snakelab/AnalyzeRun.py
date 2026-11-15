"""Record exact metrics for a completed simulation."""

from ax3l.activity.RunAnalysis import measure
from ax3l.app.snakelab.ExperimentDb import ExperimentDb
from ax3l.entities.SimulationAnalysis import SimulationAnalysis
from ax3l.interface.SnakeLab import SnakeLab


def record_run_metrics(snake: SnakeLab, experiments: ExperimentDb, run_id: str) -> SimulationAnalysis:
    saved = experiments.analysis(run_id)
    if saved is not None:
        return saved
    result = snake.get_run_result(run_id)
    if result is None or result["status"] != "completed" or result["high_score"] is None:
        raise ValueError("Metrics require a completed simulation with a recorded high score")
    metrics = measure(snake.get_analysis_episodes(run_id), result["high_score"])
    analysis = SimulationAnalysis(run_id, result["config"], metrics, None)
    experiments.save_analysis(analysis)
    return analysis
