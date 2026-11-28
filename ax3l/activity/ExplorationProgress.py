"""Prepare recorded epsilon values for the exploration chart."""


def exploration_progress(episodes: list[dict]) -> list[dict]:
    """Keep every epoch's epsilon, including zero and unmeasured values."""
    return [dict(epoch=row["episode"], epsilon=row["epsilon"])
            for row in sorted(episodes, key=lambda row: row["episode"])]
