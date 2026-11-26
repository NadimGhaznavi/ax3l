"""The editable settings and initial hypothesis for each experiment view."""

from dataclasses import dataclass

from ax3l.constants.DViewConversation import DViewConversation


@dataclass(frozen=True)
class ExperimentView:
    name: str
    parameters: tuple[str, ...]
    initial_hypothesis: str


VIEWS = {
    view.name: view for view in (
        ExperimentView("reward-signals", (
            "game.rewards.food", "game.rewards.wall", "game.rewards.snake",
            "game.rewards.empty", "game.rewards.closer_to_food", "game.rewards.further_from_food",
            "training.gamma", DViewConversation.NEW_SEED,
        ), "These reward signals encourage collecting food and discourage collisions and unproductive movement."),
        ExperimentView("architecture", (
            "model.hidden_size", "model.layers", "model.dropout", "training.sequence_length",
            DViewConversation.NEW_SEED,
        ), "This architecture and sequence length provide enough capacity and context to learn useful play."),
        ExperimentView("training", (
            "training.learning_rate", "training.batch_size", "training.sequence_length", "training.gamma",
            DViewConversation.NEW_SEED,
        ), "These training settings support consistent learning that improves scores over the run."),
        ExperimentView("exploration", (
            "epsilon.initial", "epsilon.decay", "epsilon_nice.probability", "epsilon_nice.steps",
            DViewConversation.NEW_SEED,
        ), "This exploration schedule discovers useful actions and allows increasingly effective play during training."),
    )
}
