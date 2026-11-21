"""Shared display labels and descriptions for report parameters."""

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
    "revision": "Experiment decision",
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
    "seed": DLabel.SEED,
    "epsilon_pair": DLabel.EPSILON_PAIR,
    "epsilon.initial": DLabel.EPSILON_INITIAL,
    "epsilon.decay": DLabel.EPSILON_DECAY,
    "reward_pair": DLabel.REWARD_PAIR,
    "closer_to_food": DLabel.CLOSER_TO_FOOD,
    "game.rewards.closer_to_food": DLabel.CLOSER_TO_FOOD,
    "further_from_food": DLabel.FURTHER_FROM_FOOD,
    "game.rewards.further_from_food": DLabel.FURTHER_FROM_FOOD,
    "food": DLabel.FOOD,
    "game.rewards.food": DLabel.FOOD,
    "empty": DLabel.EMPTY,
    "game.rewards.empty": DLabel.EMPTY,
    "snake": DLabel.SNAKE,
    "game.rewards.snake": DLabel.SNAKE,
    "wall": DLabel.WALL,
    "game.rewards.wall": DLabel.WALL,
    "epsilon_nice_pair": DLabel.EPSILON_NICE_PAIR,
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
    "seed": "Request the next untested seed.",
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
