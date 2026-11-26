"""Summarize recorded exploration measurements at training checkpoints."""


def exploration_progress(episodes: list[dict], window_size: int = 150) -> list[dict]:
    """Sample epsilon and weight EpsilonNice overrides by the moves in each window."""
    ordered = sorted(episodes, key=lambda row: row["episode"])
    result = []
    for offset in range(0, len(ordered), window_size):
        window = ordered[offset:offset + window_size]
        steps = sum(row["steps"] for row in window)
        overrides = sum(row["epsilon_nice_injections"] for row in window)
        result.append(dict(
            epoch=window[-1]["episode"], epsilon=window[-1]["epsilon"],
            epsilon_nice_rate=overrides / steps if steps else None,
            post_epsilon=any(row["epsilon"] == 0 for row in window),
        ))
    return result
