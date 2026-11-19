"""Short labels for Qwen's configuration choices and reference runs."""


REVISION_PARAMETER = "revision"
PARAMETER_SELECTION_SECONDS = 5 * 60
UNIQUE_CONFIG_GRACE_SECONDS = 3 * 60


CHOICE_LABELS = {
    "hidden_size": "hidden size", "layers": "encoder layers", "dropout": "dropout",
    "sequence_length": "sequence length",
    "batch_size": "batch size", "learning_rate": "learning rate", "gamma": "gamma",
    "epsilon_pair": "epsilon", "reward_pair": "distance rewards",
    "epsilon_nice_pair": "safe detours",
    "seed": "random seed",
}

PAIR_LABELS = {
    "epsilon_pair": ("start chance", "decay per episode"),
    "reward_pair": ("closer reward", "farther reward"),
    "epsilon_nice_pair": ("start chance", "moves per detour"),
}

REFERENCE_LABELS = {"latest": "latest", "golden": "golden", "all_time_best": "best"}

CHOICE_CHARTS = {
    "learning_rate": "loss",
    "epsilon_pair": "scores",
    "reward_pair": "distribution",
}
