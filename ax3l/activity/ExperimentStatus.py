"""Turn a saved configuration draft and its run into a readable report card."""

from ax3l.app.snakelab.PairParameters import PAIR_PARAMETERS
from ax3l.app.snakelab.SingleParameters import SINGLE_PARAMETERS
from ax3l.constants.DLabel import FIELD_TO_LABEL_MAP
from ax3l.constants.DSimulationAnalysis import DSimulationAnalysis
from ax3l.entities.ConfigurationDraft import ConfigurationDraft, PARAMETER_ORDER
from ax3l.entities.SimulationAnalysis import SimulationAnalysis
from ax3l.entities.AnalysisTask import AnalysisTask
from ax3l.interface.SimulationConfiguration import SCHEMA


RUN_PHASES = {
    "queued": ("Simulation queued", "Waiting for Snake Lab to start the simulation."),
    "running": ("Simulation running", "All configuration choices are saved. Snake Lab is running the simulation."),
    "paused": ("Simulation paused", "Snake Lab has paused the simulation."),
    "cancelling": ("Simulation cancelling", "Snake Lab is stopping the simulation."),
    "cancelled": ("Simulation cancelled", "The simulation was cancelled; no completed result is available."),
    "failed": ("Simulation failed", "The simulation failed; no completed result is available."),
}

REFERENCE_LABELS = {"latest": "Latest simulation", "golden": "Current golden", "all_time_best": "All-time best"}
IMAGE_LABELS = {"scores": "score trends", "distribution": "distribution", "loss": "training loss"}


def _analysis_value(analysis: SimulationAnalysis | None, sections: dict[str, str],
                    task: AnalysisTask | None) -> str:
    if analysis is not None:
        return "Complete"
    if task is not None and task.section not in sections:
        label = IMAGE_LABELS[task.section]
        if task.phase == "preparing":
            return f"Preparing {label} image"
        if task.phase == "analyzing":
            return f"Analyzing {label} image"
        if task.phase in ("failed", "stopped"):
            return f"{task.phase.capitalize()}: {label} image"
    return f"{len(sections)}/{len(DSimulationAnalysis.SECTIONS)} images analyzed"


def _prerequisites(draft: ConfigurationDraft, states: dict[str, dict]) -> list[dict]:
    roles = {}
    for role, run_id in draft.references.items():
        roles.setdefault(run_id, []).append(REFERENCE_LABELS[role])
    rows = []
    for run_id, labels in roles.items():
        state = states[run_id]
        analysis, sections, task = state["analysis"], state["sections"], state["task"]
        rows.append(dict(
            run_id=run_id, label=" / ".join(labels), selected=analysis is not None,
            value=_analysis_value(analysis, sections, task),
            current=(analysis is None and task is not None and task.phase in ("preparing", "analyzing")
                     and task.section not in sections),
            phase=task.phase if task is not None and analysis is None else None,
        ))
    return rows


def _rows(draft: ConfigurationDraft) -> list[dict]:
    rows = []
    for parameter in PARAMETER_ORDER:
        paths = ((SINGLE_PARAMETERS[parameter][0],) if parameter in SINGLE_PARAMETERS
                 else PAIR_PARAMETERS[parameter])
        for path in paths:
            value, schema = draft.config, SCHEMA
            for key in path:
                value, schema = value[key], schema["properties"][key]
            name = ".".join(path)
            rows.append(dict(
                path=name, label=FIELD_TO_LABEL_MAP[name], description=schema["description"],
                value=str(value), selected=parameter in draft.selections,
                current=parameter == draft.next_parameter,
            ))
    return rows


def _phase(draft: ConfigurationDraft, run: dict | None, comparison: dict | None,
           analysis: SimulationAnalysis | None, sections: dict[str, str],
           prerequisites: list[dict], task: AnalysisTask | None) -> tuple[str, str]:
    if draft.phase == "preparing":
        for row in prerequisites:
            if row["phase"] in ("failed", "stopped"):
                return f"Reference analysis {row['phase']}", f"{row['value']} for {row['label']}."
            if row["current"]:
                return "Preparing references", f"{row['value']} for {row['label']}."
        return "Preparing references", "Reference image analyses must be saved before configuration selection begins."
    if draft.phase == "choosing":
        return (f"Choosing: {FIELD_TO_LABEL_MAP[draft.next_parameter]}",
                "Highlighted items are awaiting selection. Checkmarks mean the LLM's choice was accepted and saved.")
    if draft.phase == "ready":
        return "Ready to submit", "All configuration choices are saved. The simulation has not been submitted yet."
    if draft.phase == "submitting":
        return ("Submission pending", "Awaiting submission confirmation. An unresolved submission is not retried automatically.")
    if run is None:
        return "Simulation unavailable", "The submitted simulation has no stored run record."
    if run["status"] != "completed":
        return RUN_PHASES[run["status"]]
    if comparison is None:
        return "Comparing results", "Simulation complete. Awaiting the saved comparison with the golden configuration."
    if analysis is None:
        if task is not None and task.phase in ("preparing", "analyzing", "failed", "stopped"):
            phase = f"Analysis {task.phase}" if task.phase in ("failed", "stopped") else "Analyzing simulation"
            return phase, f"Simulation complete. {_analysis_value(analysis, sections, task)}."
        next_section = next(label for key, label in DSimulationAnalysis.SECTIONS.items() if key not in sections)
        return "Analyzing simulation", f"Simulation complete. Awaiting analysis: {next_section}."
    return "Complete", "Simulation, golden comparison, and analysis are complete."


def experiment_status(draft: ConfigurationDraft | None, run: dict | None = None,
                      golden: dict | None = None, comparison: dict | None = None,
                      analysis: SimulationAnalysis | None = None,
                      sections: dict[str, str] | None = None,
                      reference_states: dict[str, dict] | None = None,
                      task: AnalysisTask | None = None) -> dict:
    """Use accepted selections, rather than value differences, for checkmarks."""
    if draft is None:
        return {"draft": None}
    sections = sections if sections is not None else {}
    prerequisites = _prerequisites(draft, reference_states if reference_states is not None else {})
    phase, detail = _phase(draft, run, comparison, analysis, sections, prerequisites, task)
    completed = run is not None and run["status"] == "completed"
    score = run["high_score"] if completed else None
    target = golden["high_score"]
    outcome = "Awaiting simulation"
    if completed:
        outcome = ("Awaiting comparison" if comparison is None else
                   "New golden" if comparison["current_golden_run_id"] == draft.run_id else "Golden retained")
    elif run is not None and run["status"] in ("failed", "cancelled"):
        outcome = "No completed result"
    return dict(
        draft=draft, rows=_rows(draft), prerequisites=prerequisites, phase=phase, detail=detail,
        choices_selected=len(draft.selections), choices_total=len(PARAMETER_ORDER),
        high_score=score, target_score=target,
        difference=score - target if score is not None else None, outcome=outcome,
        analysis_status=("Complete" if analysis is not None else
                         task.phase.capitalize() if task is not None and task.phase in ("failed", "stopped") else
                         f"In progress ({len(sections)}/{len(DSimulationAnalysis.SECTIONS)})" if completed else "Pending"),
    )
