"""Short labels for Qwen's configuration choices and reference runs."""


CHOICE_LABELS = {
    "hidden_size": "hidden size", "sequence_length": "sequence length",
    "batch_size": "batch size", "learning_rate": "learning rate", "gamma": "gamma",
    "epsilon_pair": "epsilon", "reward_pair": "distance rewards",
    "epsilon_nice_pair": "safe detours",
}

PAIR_LABELS = {
    "epsilon_pair": ("start chance", "decay per episode"),
    "reward_pair": ("closer reward", "farther reward"),
    "epsilon_nice_pair": ("start chance", "moves per detour"),
}

REFERENCE_LABELS = {"latest": "latest", "golden": "golden", "all_time_best": "best"}
