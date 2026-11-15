"""Keep data navigation readable and serialize actual experiment values as JSON."""

import json

from ax3l.app.snakelab.ParameterSpace import parameter_paths, parameter_values
from ax3l.constants.DChoice import REFERENCE_LABELS
from ax3l.entities.ConfigurationDraft import ConfigurationDraft, PARAMETER_ORDER
from ax3l.entities.SimulationAnalysis import SimulationAnalysis
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


CONFIG_SECTIONS = {
    "model": (("model",), ("type", "hidden_size", "heads", "layers", "dropout")),
    "training": (("training",), ("sequence_length", "batch_size", "learning_rate", "gamma",
                                  "replay_max_frames", "tau", "max_gradient_norm")),
    "rewards": (("game", "rewards"), ("food", "wall", "snake", "max_moves", "empty",
                                      "closer_to_food", "further_from_food")),
    "game": (("game",), ("board_width", "board_height", "initial_snake_length", "max_moves_multiplier")),
}
CONFIG_PAGES = (*CONFIG_SECTIONS, "exploration")
RUN_PAGES = ("scores", "endings", "activity", "notes", *CONFIG_PAGES)


PAGE_LABELS = {
    "scores": "Score statistics", "endings": "How episodes ended",
    "activity": "Moves, exploration and loss counts", "notes": "Saved notes",
    "model": "Model settings", "training": "Training settings", "exploration": "Exploration settings",
    "rewards": "Reward settings", "game": "Board settings", "config": "All settings", "rules": "Allowed values",
}


def data_json(scope: str, seed: int, data: dict) -> str:
    return json.dumps(dict(scope=scope, seed=seed, **data), ensure_ascii=False, allow_nan=False, indent=2)


def links(scope: str, pages: tuple[str, ...]) -> str:
    return "\n".join(f"[{PAGE_LABELS[page]}](/{scope}/{page})" for page in pages)


def analysis_index_page() -> str:
    return ("Settings used to produce this chart. Read current values and allowed rules before recommending a value.\n"
            + links("run", ("config", *CONFIG_PAGES, "rules")))


def analysis_rules_page(config: dict) -> str:
    constraints = ("type", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "enum")
    parameters = {}
    for parameter in PARAMETER_ORDER:
        for path in parameter_paths(parameter):
            field = SimulationConfiguration.field(path)
            parameters[".".join(path)] = {key: field[key] for key in constraints if key in field}
    return data_json("run", config["seed"], dict(
        parameters=parameters, reward_pair_rule="closer_to_food + further_from_food <= 0"))


def index_page(draft: ConfigurationDraft) -> str:
    roles = {}
    for role, run_id in draft.references.items():
        roles.setdefault(run_id, []).append(REFERENCE_LABELS[role])
    runs = "\n".join(f"[{', '.join(labels)}](/{labels[0]})" for labels in roles.values())
    return (f"[Current draft](/draft)\n{runs}\n"
            "Latest is the most recent run. Golden is the score to beat. Best is the all-time high score.\n"
            "Runs on other seeds are historical context.")


def draft_page(draft: ConfigurationDraft) -> str:
    choices = {}
    for parameter in PARAMETER_ORDER:
        choices[parameter] = dict(state="chosen" if parameter in draft.selections else "pending",
                                  values=parameter_values(draft.config, parameter))
    data = data_json("draft", draft.config["seed"], dict(choices=choices))
    return (f"The draft shows saved and inherited values.\n```json\n{data}\n```\n"
            + links("draft", CONFIG_PAGES))


def config_page(scope: str, page: str, config: dict) -> str:
    if page == "exploration":
        data = dict(epsilon=config["epsilon"], epsilon_nice=config["epsilon_nice"])
    else:
        path, fields = CONFIG_SECTIONS[page]
        values = SimulationConfiguration.value_at(config, path)
        data = {page: {key: values[key] for key in fields}}
        if page == "game":
            data["epochs"] = config["epochs"]
    return data_json(scope, config["seed"], data)


def run_overview(scope: str, draft: ConfigurationDraft, analysis: SimulationAnalysis, target: int) -> str:
    labels = [REFERENCE_LABELS[role] for role, run_id in draft.references.items()
              if run_id == analysis.run_id]
    score = analysis.metrics["high_score"]
    data = data_json(scope, analysis.config["seed"], dict(
        roles=labels, high_score=score, golden_target_score=target, score_difference=score - target,
        same_seed_as_draft=analysis.config["seed"] == draft.config["seed"]))
    return "\n".join((f"{scope} run\n```json\n{data}\n```",
                      "Same seed as draft." if analysis.config["seed"] == draft.config["seed"] else
                      "Different seed: historical context, not a controlled comparison.",
                      links(scope, tuple(page for page in RUN_PAGES if page != "notes" or analysis.summary))))


def run_page(scope: str, page: str, analysis: SimulationAnalysis) -> str:
    if page in CONFIG_PAGES:
        return config_page(scope, page, analysis.config)
    metrics = analysis.metrics
    if page == "scores":
        fields = ("episodes", "high_score", "mean_score", "median_score", "mean_first_50_scores",
                  "mean_last_50_scores", "zero_score_episodes", "high_score_episodes")
        data = {key: metrics[key] for key in fields}
    elif page == "endings":
        data = dict(episodes=metrics["episodes"], termination_reasons=metrics["termination_reasons"])
    elif page == "activity":
        fields = ("total_steps", "epsilon_random_actions", "nice_overrides", "episodes_with_loss")
        data = {key: metrics[key] for key in fields}
    elif page == "notes":
        data = dict(summary=analysis.summary)
    return data_json(scope, analysis.config["seed"], data)
