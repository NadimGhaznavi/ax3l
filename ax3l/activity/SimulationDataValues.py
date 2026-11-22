"""Prepare experiment values independently of their page presentation."""

from ax3l.app.snakelab.ParameterSpace import parameter_paths
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


def scoped_values(scope: str, seed: int, data: dict) -> dict:
    return dict(scope=scope, seed=seed, **data)


def draft_values(draft: ConfigurationDraft) -> dict:
    return scoped_values("draft", draft.config["seed"], dict(
        phase=draft.phase, saved_settings=draft.selections,
        current_setting=draft.next_parameter, config=draft.config))


def config_values(scope: str, page: str, config: dict) -> dict:
    if page == "exploration":
        data = dict(epsilon=config["epsilon"], epsilon_nice=config["epsilon_nice"])
    else:
        path, fields = CONFIG_SECTIONS[page]
        values = SimulationConfiguration.value_at(config, path)
        data = {page: {key: values[key] for key in fields}}
        if page == "game":
            data["epochs"] = config["epochs"]
    return scoped_values(scope, config["seed"], data)


def run_result_values(scope: str, draft: ConfigurationDraft, analysis: SimulationAnalysis, target: int) -> dict:
    score = analysis.metrics["high_score"]
    return scoped_values(scope, analysis.config["seed"], dict(
        high_score=score, golden_target_score=target, score_difference=score - target,
        same_seed_as_draft=analysis.config["seed"] == draft.config["seed"],
        metrics=analysis.metrics, summary=analysis.summary))


def run_snapshot_values(scope: str, draft: ConfigurationDraft, analysis: SimulationAnalysis, target: int) -> dict:
    return dict(run_result_values(scope, draft, analysis, target), config=analysis.config)


def run_values(scope: str, page: str, analysis: SimulationAnalysis) -> dict:
    if page in CONFIG_PAGES:
        return config_values(scope, page, analysis.config)
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
    return scoped_values(scope, analysis.config["seed"], data)


def parameter_rules() -> dict:
    constraints = ("type", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "enum")
    parameters = {}
    for parameter in PARAMETER_ORDER:
        if parameter == "seed":
            continue
        for path in parameter_paths(parameter):
            field = SimulationConfiguration.field(path)
            parameters[".".join(path)] = {key: field[key] for key in constraints if key in field}
    return parameters
