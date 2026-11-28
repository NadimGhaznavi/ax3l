"""Present the active experiment and its selection and evaluation conversations."""

from collections import defaultdict
import json

from ax3l.activity.ViewConfiguration import view_values
from ax3l.constants.DAx3l import DAx3l
from ax3l.constants.DEventCategory import DEventCategory as Events
from ax3l.constants.DLabel import FIELD_TO_DESCRIPTION_MAP, FIELD_TO_LABEL_MAP
from ax3l.entities.ExperimentView import VIEWS
from ax3l.presentation.reporting.ReplyReport import reasoning_content, response_usage


VIEW_LABELS = {"reward-signals": "Reward Signals", "architecture": "Architecture",
               "training": "Training", "exploration": "Exploration"}


def _value(value):
    return "—" if value is None else json.dumps(value, ensure_ascii=False)


def _elapsed(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"


def experiment_totals(sections: list[dict]) -> dict:
    """Sum the recorded conversation metrics across the displayed conversations."""
    totals = {}
    for key in ("elapsed_seconds", "input_tokens", "output_tokens"):
        recorded = [section[key] for section in sections if section[key] is not None]
        totals[key] = sum(recorded) if recorded else None
    totals["elapsed"] = _elapsed(totals.pop("elapsed_seconds"))
    return totals


def experiment_summary(data: dict, sections: list[dict]) -> dict:
    """Describe the saved phase and recorded simulation without inventing prompts."""
    state = data["state"]
    if state is None:
        return dict(title="No active experiment", phase="Waiting for initialization", simulation=None,
                    seed=None, failures=None, loss_limit=DAx3l.SEED_ROTATION_FAILURES)
    baseline = state.baseline or state.seed_baseline
    title = ("Default baseline" if state.baseline else "Seed rotation baseline" if state.seed_baseline
             else VIEW_LABELS[state.view_name])
    phase = {
        "choosing": "Selecting parameters", "revising": "Revising duplicate configuration",
        "ready": "Ready to submit simulation", "submitting": "Submitting simulation",
        "running": "Running simulation", "comparing": "Comparing results",
        "evaluating": "Evaluating results", "completed": "Completed",
    }[state.phase]
    for section in sections:
        if section["status"] in ("Failed", "Interrupted"):
            phase = f"{section['stage'].capitalize()} {section['status'].lower()}"
    reference, candidate = data["reference_run"], data["candidate_run"]
    simulation_status = (candidate["status"].capitalize() if candidate else
                         "Submitting" if state.phase == "submitting" else
                         "Awaiting selection" if state.phase in ("choosing", "revising") else
                         "Awaiting submission")
    if candidate and candidate["status"] in ("failed", "cancelled"):
        phase = f"Simulation {candidate['status']}"
    elif candidate and state.phase == "running":
        phase = ("Awaiting comparison" if candidate["status"] == "completed" else
                 f"Simulation {candidate['status']}")
    reference_score = reference["high_score"] if reference and reference["status"] == "completed" else None
    candidate_score = candidate["high_score"] if candidate and candidate["status"] == "completed" else None
    outcome = "Awaiting simulation results."
    if state.phase == "comparing" or (candidate and candidate["status"] == "completed"):
        outcome = "Awaiting comparison."
    if state.phase in ("evaluating", "completed"):
        if baseline:
            outcome = "Golden baseline established."
        elif state.golden_run_id == state.run_id:
            tied = candidate_score is not None and candidate_score == reference_score
            outcome = "Promoted to golden (tie)." if tied else "Promoted to golden."
        else:
            outcome = "Golden retained."
    elif candidate and candidate["status"] in ("failed", "cancelled"):
        outcome = "Experiment stopped before comparison."
    return dict(title=title, phase=phase, seed=state.config["seed"], failures=state.failures,
                loss_limit=DAx3l.SEED_ROTATION_FAILURES, simulation=dict(
                    baseline=baseline, status=simulation_status, run_id=state.run_id,
                    reference_run_id=state.reference_run_id, reference_score=reference_score,
                    candidate_score=candidate_score, outcome=outcome))


def experiment_sections(data: dict) -> list[dict]:
    state = data["state"]
    if state is None or state.baseline or state.seed_baseline:
        return []
    name = state.view_name
    view = VIEWS[name]
    conversations = defaultdict(list)
    for event in data["events"]:
        conversations[event["parent_event_id"]].append(event)
    latest = {}
    for events in conversations.values():
        prompt = next((event for event in events if event["category"] == Events.Conversation.CATEGORY
                       and event["name"] == Events.Conversation.PROMPT), None)
        if prompt is None:
            continue
        stage = prompt["source_name"]
        if prompt["process_id"] == state.experiment_id and prompt["parameter"] == name:
            latest[stage] = events

    sections = []
    for stage in ("selection", "evaluation"):
        events = latest.get(stage, [])
        by_name = {event["name"]: event for event in events}
        prompt = by_name.get(Events.Conversation.PROMPT)
        response = by_name.get(Events.Conversation.RESPONSE)
        ended = by_name.get(Events.Conversation.ENDED)
        accepted = by_name.get(Events.Tool.COMPLETED)
        submission = json.loads(accepted["content"]) if accepted else {}
        usage = response_usage(response["content"]) if response else {}
        proposal = state.proposals.get(name)
        selected = submission.get("values", {})
        status = "Saved" if accepted else "Waiting"
        if ended and ended["log_level"] == "ERROR":
            status = "Failed"
        elif ended and not accepted:
            status = "Interrupted"
        elif prompt and not ended and not accepted:
            status = "In progress"

        if not prompt and stage == "evaluation" and state.phase not in ("evaluating", "completed"):
            status = "Awaiting simulation results"
        elif stage == "selection" and state.phase == "revising" and accepted:
            status = "Revision required"

        baseline = data["selection_config"]
        choices = data["latest_config"] if stage == "evaluation" else None
        baseline_values = view_values(view, baseline) if baseline else {}
        choice_values = view_values(view, choices) if choices else selected.copy()
        hypothesis = proposal.hypothesis if stage == "evaluation" and proposal else None
        if stage == "selection":
            hypothesis = submission.get("hypothesis")
        rows = [dict(
            label=FIELD_TO_LABEL_MAP.get(path, path),
            description=FIELD_TO_DESCRIPTION_MAP.get(path, ""),
            baseline=_value(baseline_values.get(path)), choice=_value(choice_values.get(path)),
            saved=stage == "selection" and path in selected,
            shared=None,
            changed=path in choice_values and path in baseline_values
                    and choice_values[path] != baseline_values[path],
        ) for path in view.parameters]
        start = by_name.get(Events.LLM.REQUEST_STARTED, prompt)
        elapsed_seconds = None
        if start:
            end = ended["occurred_at"] if ended else start["observed_at"]
            elapsed_seconds = max(0, int((end - start["occurred_at"]).total_seconds()))
        sections.append(dict(
            id=f"{stage}-{name}", title=f"{VIEW_LABELS[name]} {'Evaluation' if stage == 'evaluation' else 'Selection'}",
            stage=stage, status=status, saved=bool(accepted),
            prompt_id=prompt["event_id"] if prompt else None,
            response_id=response["event_id"] if response else None,
            has_reason=bool(response and reasoning_content(response["content"])),
            elapsed=_elapsed(elapsed_seconds), elapsed_seconds=elapsed_seconds,
            input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
            hypothesis=hypothesis, observations=submission.get("observations"),
            error=ended["content"] if status in ("Failed", "Interrupted") else None,
            rows=rows, open=status in ("In progress", "Failed"),
        ))
    return sections
