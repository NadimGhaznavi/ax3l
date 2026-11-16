"""Turn a saved configuration draft and its setup steps into a status report."""

from ax3l.app.snakelab.ParameterSpace import parameter_paths
from ax3l.constants.DLabel import FIELD_TO_LABEL_MAP
from ax3l.constants.DChoice import REVISION_PARAMETER
from ax3l.entities.ConfigurationDraft import ConfigurationDraft, PARAMETER_ORDER
from ax3l.entities.SimulationAnalysis import SimulationAnalysis
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


RUN_PHASES = {
    "queued": ("Simulation queued", "Waiting for Snake Lab to start the simulation."),
    "running": ("Simulation running", "All configuration choices are saved. Snake Lab is running the simulation."),
    "paused": ("Simulation paused", "Snake Lab has paused the simulation."),
    "cancelling": ("Simulation cancelling", "Snake Lab is stopping the simulation."),
    "cancelled": ("Simulation cancelled", "The simulation was cancelled."),
    "failed": ("Simulation failed", "Snake Lab reported a failed simulation."),
}


def _elapsed(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    clock = f"{minutes:02}:{seconds:02}"
    return f"{hours:02}:{clock}" if hours else clock


def _rows(draft: ConfigurationDraft, activity: dict[str, dict]) -> list[dict]:
    rows = []
    for parameter in PARAMETER_ORDER:
        paths = parameter_paths(parameter)
        for path in paths:
            name = ".".join(path)
            rows.append(dict(
                path=name, label=FIELD_TO_LABEL_MAP[name],
                description=SimulationConfiguration.field(path)["description"],
                value=str(SimulationConfiguration.value_at(draft.config, path)),
                selected=parameter in draft.selections, current=parameter == draft.next_parameter,
                steps=[], image_url=None,
            ))
        work = activity.get(parameter)
        if work:
            rows[-1]["steps"] = [dict(step, elapsed=_elapsed(step["seconds"])) for step in work["steps"]]
            image = work["image_event_id"]
            rows[-len(paths)]["image_url"] = f"/events/{image}" if image is not None else None
    if draft.phase == "selecting_parameter" or REVISION_PARAMETER in activity:
        work = activity.get(REVISION_PARAMETER)
        rows.append(dict(
            path=REVISION_PARAMETER, label=FIELD_TO_LABEL_MAP[REVISION_PARAMETER],
            description="Choose which saved setting to change after a duplicate configuration.",
            value="Choosing" if draft.phase == "selecting_parameter" else "Selected",
            selected=None, current=draft.phase == "selecting_parameter", image_url=None,
            steps=[dict(step, elapsed=_elapsed(step["seconds"])) for step in work["steps"]] if work else [],
        ))
    return rows


def _phase(draft: ConfigurationDraft, run: dict | None, comparison: dict | None,
           analysis: SimulationAnalysis | None) -> tuple[str, str]:
    if draft.phase == "preparing":
        return "Preparing references", "Loading measured data for the reference runs."
    if draft.phase == "choosing":
        return (f"Choosing {FIELD_TO_LABEL_MAP[draft.next_parameter]}",
                "A checkmark indicates that Ax3l accepted and saved the choice.")
    if draft.phase == "selecting_parameter":
        return ("Choosing a setting to revise",
                "The complete configuration is a duplicate. Qwen will choose which setting to change.")
    if draft.phase == "ready":
        return "Ready to submit", "All configuration choices are saved."
    if draft.phase == "submitting":
        return "Submission pending", "Waiting for Snake Lab to confirm the simulation."
    if run is None:
        return "Simulation unavailable", "The submitted simulation has no stored run record."
    if run["status"] != "completed":
        return RUN_PHASES[run["status"]]
    if comparison is None:
        return "Comparing results", "Comparing the high score with the golden configuration."
    if analysis is None:
        return "Recording results", "Saving the measured results."
    return "Complete", "The simulation results and golden comparison are saved."


def experiment_status(draft: ConfigurationDraft | None, run: dict | None = None,
                      golden: dict | None = None, comparison: dict | None = None,
                      analysis: SimulationAnalysis | None = None,
                      activity: dict[str, dict] | None = None) -> dict:
    if draft is None:
        return {"draft": None}
    phase, detail = _phase(draft, run, comparison, analysis)
    completed = run is not None and run["status"] == "completed"
    score = run["high_score"] if completed else None
    target = golden["high_score"]
    outcome = "Awaiting simulation"
    if completed:
        outcome = ("Awaiting comparison" if comparison is None else
                   "New golden" if comparison["current_golden_run_id"] == draft.run_id else "Golden retained")
    elif run is not None and run["status"] in ("failed", "cancelled"):
        outcome = "No completed result"
    rows = _rows(draft, activity or {})
    steps = [step for row in rows for step in row["steps"]]
    seconds = sum(step["seconds"] for step in steps if step["seconds"] is not None)
    input_tokens = sum(step["input_tokens"] for step in steps if step["input_tokens"] is not None)
    output_tokens = sum(step["output_tokens"] for step in steps if step["output_tokens"] is not None)
    return dict(
        draft=draft, rows=rows, phase=phase, detail=detail,
        totals=dict(elapsed=_elapsed(seconds), input_tokens=input_tokens,
                    output_tokens=output_tokens, tokens=input_tokens + output_tokens),
        choices_selected=len(draft.selections), choices_total=len(PARAMETER_ORDER),
        high_score=score, target_score=target,
        difference=score - target if score is not None else None, outcome=outcome,
        analysis_status=("Saved" if analysis is not None else "Recording" if completed else "Pending"),
    )
