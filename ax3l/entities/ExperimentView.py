"""The editable settings for each experiment view."""

from dataclasses import dataclass

from ax3l.constants.DViewConversation import DViewConversation


@dataclass(frozen=True)
class ExperimentView:
    name: str
    parameters: tuple[str, ...]


VIEWS = {
    view.name: view for view in (
        ExperimentView("reward-signals", (
            "game.rewards.food", "game.rewards.wall", "game.rewards.snake",
            "game.rewards.empty", "game.rewards.closer_to_food", "game.rewards.further_from_food",
            "training.gamma", DViewConversation.NEW_SEED,
        )),
        ExperimentView("architecture", (
            "model.hidden_size", "model.layers", "model.dropout", "training.sequence_length",
            DViewConversation.NEW_SEED,
        )),
        ExperimentView("training", (
            "training.learning_rate", "training.batch_size", "training.sequence_length", "training.gamma",
            DViewConversation.NEW_SEED,
        )),
        ExperimentView("exploration", (
            "epsilon.initial", "epsilon.decay", "epsilon_nice.probability", "epsilon_nice.steps",
            DViewConversation.NEW_SEED,
        )),
    )
}
