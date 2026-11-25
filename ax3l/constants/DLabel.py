"""Shared display labels and descriptions for report parameters."""

from typing import Final


class DLabel:
    HIDDEN_SIZE: Final[str] = "Hidden Size"
    LAYERS: Final[str] = "Encoder Layers"
    DROPOUT: Final[str] = "Dropout"
    SEQUENCE_LENGTH: Final[str] = "Sequence Length"
    BATCH_SIZE: Final[str] = "Batch Size"
    LEARNING_RATE: Final[str] = "Learning Rate"
    GAMMA: Final[str] = "Gamma"
    SEED: Final[str] = "Random Seed"
    EPSILON_PAIR: Final[str] = "Epsilon: initial, decay"
    EPSILON_INITIAL: Final[str] = "Epsilon: initial"
    EPSILON_DECAY: Final[str] = "Epsilon: decay"
    REWARD_PAIR: Final[str] = "Food Reward: closer, further"
    CLOSER_TO_FOOD: Final[str] = "Food Reward: closer"
    FURTHER_FROM_FOOD: Final[str] = "Food Reward: further"
    FOOD: Final[str] = "Food Reward"
    EMPTY: Final[str] = "Empty Space Reward"
    SNAKE: Final[str] = "Snake Collision Reward"
    WALL: Final[str] = "Wall Collision Reward"
    EPSILON_NICE_PAIR: Final[str] = "EpsilonNice: probability, steps"
    EPSILON_NICE_PROBABILITY: Final[str] = "EpsilonNice: probability"
    EPSILON_NICE_STEPS: Final[str] = "EpsilonNice: steps"


FIELD_TO_LABEL_MAP: Final[dict[str, str]] = {
    "configuration": "Complete configuration",
    "model.hidden_size": DLabel.HIDDEN_SIZE,
    "model.layers": DLabel.LAYERS,
    "model.dropout": DLabel.DROPOUT,
    "training.sequence_length": DLabel.SEQUENCE_LENGTH,
    "training.batch_size": DLabel.BATCH_SIZE,
    "training.learning_rate": DLabel.LEARNING_RATE,
    "training.gamma": DLabel.GAMMA,
    "seed": DLabel.SEED,
    "epsilon.initial": DLabel.EPSILON_INITIAL,
    "epsilon.decay": DLabel.EPSILON_DECAY,
    "game.rewards.closer_to_food": DLabel.CLOSER_TO_FOOD,
    "game.rewards.further_from_food": DLabel.FURTHER_FROM_FOOD,
    "game.rewards.food": DLabel.FOOD,
    "game.rewards.empty": DLabel.EMPTY,
    "game.rewards.snake": DLabel.SNAKE,
    "game.rewards.wall": DLabel.WALL,
    "epsilon_nice.probability": DLabel.EPSILON_NICE_PROBABILITY,
    "epsilon_nice.steps": DLabel.EPSILON_NICE_STEPS,
    "model.type": "Model",
    "model.heads": "Attention Heads",
}


FIELD_TO_DESCRIPTION_MAP: Final[dict[str, str]] = {
    "model.hidden_size": "Hidden width of the Transformer.",
    "model.layers": "Number of Transformer encoder layers.",
    "model.dropout": "Model dropout probability.",
    "training.sequence_length": "Consecutive training frames.",
    "training.batch_size": "Training batch size",
    "training.learning_rate": "Optimizer learning rate",
    "training.gamma": "Discount factor",
    "seed": "Random seed used for the simulation.",
    "epsilon.initial": "Initial probability",
    "epsilon.decay": "Probability decay rate",
    "game.rewards.closer_to_food": "",
    "game.rewards.further_from_food": "",
    "game.rewards.food": "Reward for eating food.",
    "game.rewards.empty": "Reward for a move without food.",
    "game.rewards.snake": "Penalty for colliding with the snake.",
    "game.rewards.wall": "Penalty for colliding with a wall.",
    "epsilon_nice.probability": "Invocation probability",
    "epsilon_nice.steps": "Safe detour steps",
}
