"""Choose readable axis intervals that are multiples of five."""

from collections.abc import Iterable
from math import ceil, floor, log10


def tick_step(span: float, intervals: int = 6) -> int:
    """Keep roughly the requested interval count, with a minimum step of five."""
    minimum = max(5, span / intervals)
    unit = 5 * 10 ** floor(log10(minimum / 5))
    return ceil(minimum / unit) * unit


def axis_ticks(values: Iterable[float | None]) -> dict:
    """Anchor ticks at zero and include enclosing ticks for narrow data ranges."""
    values = [value for value in values if value is not None]
    low, high = min(values, default=0), max(values, default=0)
    step = tick_step(max(0, high) - min(0, low))
    return dict(tickmode="linear", tick0=0, dtick=step,
                autorangeoptions=dict(include=[floor(low / step) * step, ceil(high / step) * step]))
