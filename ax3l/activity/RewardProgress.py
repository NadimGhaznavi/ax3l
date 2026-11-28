"""Summarize food per recorded move and terminal collisions per episode."""


def reward_progress(episodes: list[dict], window_size: int = 150) -> list[dict]:
    """Use food per 100 moves and collision shares; missing measurements leave gaps."""
    ordered = sorted(episodes, key=lambda row: row["episode"])
    result = []
    for offset in range(0, len(ordered), window_size):
        window = ordered[offset:offset + window_size]
        steps = sum(row["steps"] for row in window)
        outcomes_recorded = all(row["outcome"] is not None for row in window)
        result.append(dict(
            epoch=window[-1]["episode"],
            food=100 * sum(row["score"] for row in window) / steps if steps else None,
            wall=sum(row["outcome"] == "wall" for row in window) / len(window)
            if outcomes_recorded else None,
            snake=sum(row["outcome"] == "snake" for row in window) / len(window)
            if outcomes_recorded else None,
        ))
    return result
