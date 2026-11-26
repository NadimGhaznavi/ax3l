"""Summarize recorded episode losses in consecutive training windows."""


def training_progress(episodes: list[dict], window_size: int = 150) -> list[dict]:
    """Average recorded losses, including zero; leave wholly unmeasured windows as gaps."""
    ordered = sorted(episodes, key=lambda row: row["episode"])
    result = []
    for offset in range(0, len(ordered), window_size):
        window = ordered[offset:offset + window_size]
        losses = [row["loss"] for row in window if row["loss"] is not None]
        result.append(dict(epoch=window[-1]["episode"], loss=sum(losses) / len(losses) if losses else None))
    return result
