"""Hold one conversation's deadline and expose its signed countdown."""

from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True)
class ConversationTimer:
    deadline: float

    def remaining(self, now: float) -> str:
        """Read whole seconds remaining, including overtime, as MM:SS."""
        seconds = ceil(self.deadline - now)
        minutes, seconds_part = divmod(abs(seconds), 60)
        return f"{'-' if seconds < 0 else ''}{minutes:02d}:{seconds_part:02d}"
