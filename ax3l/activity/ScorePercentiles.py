"""Summarize recorded episode scores in consecutive training windows."""

from math import ceil, floor


def score_percentiles(episodes: list[dict], window_size: int = 150) -> list[dict]:
    """Use linear interpolation and retain the final partial window."""
    ordered = sorted(episodes, key=lambda row: row["episode"])
    result = []
    for offset in range(0, len(ordered), window_size):
        window = ordered[offset:offset + window_size]
        scores = sorted(row["score"] for row in window)
        point = dict(epoch=window[-1]["episode"])
        for name, percentile in (("p90", .9), ("p25", .25)):
            position = (len(scores) - 1) * percentile
            fraction = position - floor(position)
            point[name] = scores[floor(position)] * (1 - fraction) + scores[ceil(position)] * fraction
        result.append(point)
    return result
