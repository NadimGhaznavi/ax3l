"""The editable settings for each experiment view."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExperimentView:
    name: str
    parameters: tuple[str, ...]


VIEWS = {
    view.name: view for view in (
        ExperimentView("reward-signals", (
            "game.rewards.food", "game.rewards.wall", "game.rewards.snake",
            "game.rewards.empty", "game.rewards.closer_to_food", "game.rewards.further_from_food",
            "training.gamma",
        )),
        ExperimentView("architecture", (
            "model.hidden_size", "model.layers", "model.dropout", "training.sequence_length",
        )),
        ExperimentView("training", (
            "training.learning_rate", "training.batch_size", "training.sequence_length", "training.gamma",
        )),
        ExperimentView("exploration", (
            "epsilon.initial", "epsilon.decay", "epsilon_nice.probability", "epsilon_nice.steps",
        )),
    )
}
