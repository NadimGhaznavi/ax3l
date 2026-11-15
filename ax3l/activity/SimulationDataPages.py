"""Render one small English page from a draft or saved run analysis."""

from ax3l.app.snakelab.PairParameters import PAIR_PARAMETERS
from ax3l.app.snakelab.SingleParameters import SINGLE_PARAMETERS
from ax3l.constants.DChoice import CHOICE_LABELS, PAIR_LABELS, REFERENCE_LABELS
from ax3l.entities.ConfigurationDraft import ConfigurationDraft, PARAMETER_ORDER
from ax3l.entities.SimulationAnalysis import SimulationAnalysis


CONFIG_SECTIONS = {
    "model": (("model",), {"type": "model", "hidden_size": "hidden size",
                            "heads": "heads", "layers": "layers", "dropout": "dropout"}),
    "training": (("training",), {"sequence_length": "sequence length", "batch_size": "batch size",
                                  "learning_rate": "learning rate", "gamma": "gamma",
                                  "replay_max_frames": "replay frames", "tau": "target update rate",
                                  "max_gradient_norm": "gradient limit"}),
    "rewards": (("game", "rewards"), {"food": "food", "wall": "wall", "snake": "body",
                                      "max_moves": "move limit", "empty": "empty move",
                                      "closer_to_food": "closer", "further_from_food": "farther"}),
    "game": (("game",), {"board_width": "board width", "board_height": "board height",
                          "initial_snake_length": "starting length", "max_moves_multiplier": "move multiplier"}),
}
CONFIG_PAGES = (*CONFIG_SECTIONS, "exploration")
RUN_PAGES = ("scores", "endings", "activity", "notes", *CONFIG_PAGES)


def value_at(config: dict, path: tuple[str, ...]):
    for key in path:
        config = config[key]
    return config


def shown(value) -> str:
    return "unrecorded" if value is None else str(value)


def links(scope: str, pages: tuple[str, ...]) -> str:
    return "\n".join(f"[{page}](/{scope}/{page})" for page in pages)


def index_page(draft: ConfigurationDraft) -> str:
    roles = {}
    for role, run_id in draft.references.items():
        roles.setdefault(run_id, []).append(REFERENCE_LABELS[role])
    runs = "\n".join(f"[{', '.join(labels)}](/{labels[0]})" for labels in roles.values())
    return (f"[draft](/draft): current choices\n{runs}\n"
            "Latest: feedback. Golden: baseline. Best: historical best.\n"
            "Shared labels mean the same run. Different seeds are not controlled comparisons.")


def draft_page(draft: ConfigurationDraft) -> str:
    lines = [f"Draft | seed {draft.config['seed']}", "Chosen = saved; pending = inherited."]
    for parameter in PARAMETER_ORDER:
        state = "chosen" if parameter in draft.selections else "pending"
        if parameter in SINGLE_PARAMETERS:
            value = value_at(draft.config, SINGLE_PARAMETERS[parameter][0])
            text = str(value)
        else:
            text = ", ".join(f"{label} {value_at(draft.config, path)}"
                             for label, path in zip(PAIR_LABELS[parameter], PAIR_PARAMETERS[parameter]))
        lines.append(f"{CHOICE_LABELS[parameter]}: {text} ({state})")
    lines.append(links("draft", CONFIG_PAGES))
    return "\n".join(lines)


def config_page(scope: str, page: str, config: dict) -> str:
    lines = [f"{scope} {page} | seed {config['seed']}"]
    if page == "exploration":
        epsilon, nice = config["epsilon"], config["epsilon_nice"]
        lines.extend((f"Epsilon: start {epsilon['initial']}; floor {epsilon['minimum']}; decay {epsilon['decay']} per episode.",
                      f"Safe detours: chance {nice['probability']}; moves {nice['steps']}."))
    else:
        path, labels = CONFIG_SECTIONS[page]
        values = value_at(config, path)
        lines.extend(f"{label}: {values[key]}" for key, label in labels.items())
        if page == "game":
            lines.append(f"Episodes: {config['epochs']}")
            lines.append("Move limit = move multiplier times current snake length.")
    return "\n".join(lines)


def run_overview(scope: str, draft: ConfigurationDraft, analysis: SimulationAnalysis, target: int) -> str:
    labels = [REFERENCE_LABELS[role] for role, run_id in draft.references.items()
              if run_id == analysis.run_id]
    score = analysis.metrics["high_score"]
    return "\n".join((f"{scope} run | seed {analysis.config['seed']}",
                      "Roles: " + ", ".join(labels),
                      f"High score: {score}; golden target: {target}; gap: {score - target}.",
                      "Same seed as draft." if analysis.config['seed'] == draft.config['seed'] else
                      "Different seed: historical context, not a controlled comparison.",
                      links(scope, RUN_PAGES)))


def run_page(scope: str, page: str, analysis: SimulationAnalysis) -> str:
    if page in CONFIG_PAGES:
        return config_page(scope, page, analysis.config)
    metrics = analysis.metrics
    lines = [f"{scope} {page} | seed {analysis.config['seed']}"]
    if page == "scores":
        fields = {"episodes": "episodes", "high_score": "high score", "mean_score": "mean score",
                  "median_score": "median score", "mean_first_50_scores": "first 50 mean",
                  "mean_last_50_scores": "last 50 mean", "zero_score_episodes": "zero scores",
                  "high_score_episodes": "high-score episodes"}
        lines.extend(f"{label}: {shown(metrics[key])}" for key, label in fields.items())
    elif page == "endings":
        labels = {"wall": "wall", "snake": "body", "max_moves": "move limit",
                  "board_filled": "board filled", "unrecorded_or_other": "other or unrecorded"}
        lines.append(f"Episodes: {metrics['episodes']}. Percentages rounded to one decimal.")
        for key, label in labels.items():
            ending = metrics["termination_reasons"][key]
            lines.append(f"{label}: {ending['count']} ({ending['percent']:.1f}%)")
    elif page == "activity":
        fields = {"total_steps": "total moves", "epsilon_random_actions": "epsilon random moves",
                  "nice_overrides": "safe detour moves", "episodes_with_loss": "episodes with loss"}
        lines.extend(f"{label}: {metrics[key]}" for key, label in fields.items())
    elif page == "notes":
        lines.append(analysis.summary)
    return "\n".join(lines)
