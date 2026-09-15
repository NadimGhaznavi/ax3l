"""Format value changes captured in golden configuration decision events."""

import re


def parameter_change(decision: str | None) -> str:
    """Show recorded before/after values; label each value for joint changes."""
    number = r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?"
    changes = re.findall(
        rf"(?:^|; )([\w.]+): ({number}) -> ({number})(?=; |\.$|$)",
        decision or "",
    )
    if len(changes) == 1:
        _, before, after = changes[0]
        return f"{before} > {after}"
    return "; ".join(f"{name}: {before} > {after}" for name, before, after in changes)
