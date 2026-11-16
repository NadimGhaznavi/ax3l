"""Shared display labels for report parameters."""

from typing import Final


class DLabel:
    # Pair labels follow the component order in PairParameters.PAIR_PARAMETERS.

    HIDDEN_SIZE: Final[str] = "Hidden Size"
    LAYERS: Final[str] = "Encoder Layers"
    DROPOUT: Final[str] = "Dropout"
    SEQUENCE_LENGTH: Final[str] = "Sequence Length"
    BATCH_SIZE: Final[str] = "Batch Size"
    LEARNING_RATE: Final[str] = "Learning Rate"
    GAMMA: Final[str] = "Gamma"
    EPSILON_PAIR: Final[str] = "Epsilon: initial, decay"
    EPSILON_INITIAL: Final[str] = "Epsilon: initial"
    EPSILON_DECAY: Final[str] = "Epsilon: decay"
    REWARD_PAIR: Final[str] = "Food Reward: closer, further"
    CLOSER_TO_FOOD: Final[str] = "Food Reward: closer"
    FURTHER_FROM_FOOD: Final[str] = "Food Reward: further"
    EPSILON_NICE_PAIR: Final[str] = "EpsilonNice: probability, steps"
    EPSILON_NICE_PROBABILITY: Final[str] = "EpsilonNice: probability"
    EPSILON_NICE_STEPS: Final[str] = "EpsilonNice: steps"


FIELD_TO_LABEL_MAP: Final[dict[str, str]] = {
    "configuration": "Complete configuration",
    "simulation_summary": "Simulation analysis",
    "hidden_size": DLabel.HIDDEN_SIZE,
    "model.hidden_size": DLabel.HIDDEN_SIZE,
    "layers": DLabel.LAYERS,
    "model.layers": DLabel.LAYERS,
    "dropout": DLabel.DROPOUT,
    "model.dropout": DLabel.DROPOUT,
    "sequence_length": DLabel.SEQUENCE_LENGTH,
    "training.sequence_length": DLabel.SEQUENCE_LENGTH,
    "batch_size": DLabel.BATCH_SIZE,
    "training.batch_size": DLabel.BATCH_SIZE,
    "learning_rate": DLabel.LEARNING_RATE,
    "training.learning_rate": DLabel.LEARNING_RATE,
    "gamma": DLabel.GAMMA,
    "training.gamma": DLabel.GAMMA,
    "epsilon_pair": DLabel.EPSILON_PAIR,
    "epsilon.initial": DLabel.EPSILON_INITIAL,
    "epsilon.decay": DLabel.EPSILON_DECAY,
    "reward_pair": DLabel.REWARD_PAIR,
    "closer_to_food": DLabel.CLOSER_TO_FOOD,
    "game.rewards.closer_to_food": DLabel.CLOSER_TO_FOOD,
    "further_from_food": DLabel.FURTHER_FROM_FOOD,
    "game.rewards.further_from_food": DLabel.FURTHER_FROM_FOOD,
    "epsilon_nice_pair": DLabel.EPSILON_NICE_PAIR,
    "epsilon_nice.probability": DLabel.EPSILON_NICE_PROBABILITY,
    "epsilon_nice.steps": DLabel.EPSILON_NICE_STEPS,
    "model.type": "Model",
    "model.heads": "Attention Heads",
}
