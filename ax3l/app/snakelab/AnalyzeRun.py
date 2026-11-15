"""Generate and save a completed run's interpretation once."""

import asyncio

from ax3l.activity.RunAnalysis import measure, render_analysis
from ax3l.app.snakelab.ExperimentDb import ExperimentDb
from ax3l.app.snakelab.ToolConversation import converse
from ax3l.app.snakelab.prompts.AnalyzeSimulation import AnalyzeSimulation
from ax3l.constants.DSimulationAnalysis import DSimulationAnalysis
from ax3l.interface.SnakeLabTools import SnakeLabTools


async def analyze_run(snake, llm, output, db, endpoint, run_id: str, target_score: int):
    experiments = ExperimentDb(db)
    saved = experiments.analysis(run_id)
    if saved is not None:
        return saved
    result = snake.get_run_result(run_id)
    if result is None or result["status"] != "completed" or result["high_score"] is None:
        raise ValueError("Analysis requires a completed simulation with a recorded high score")
    episodes = snake.get_analysis_episodes(run_id)
    metrics = measure(episodes, result["high_score"])
    sections = experiments.analysis_sections(run_id)
    for section in DSimulationAnalysis.SECTIONS:
        if section in sections:
            continue
        png = await asyncio.to_thread(render_analysis, run_id, result["config"], episodes,
                                      metrics, target_score, section)
        prompt = AnalyzeSimulation(run_id, result["config"], metrics, png, section)
        async with SnakeLabTools(endpoint, "simulation_summary", run_id=run_id, section=section) as tools:
            await converse(llm, output, db, tools, [prompt],
                           parameter="simulation_summary", process_id=run_id)
    return experiments.analysis(run_id)
