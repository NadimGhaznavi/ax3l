"""Explain an illegal proposal to the LLM."""

from ax3l.app.Prompt import Prompt


class InvalidValue(Prompt):
    def __init__(self, reason: str):
        super().__init__(f"{reason} Submit a legal value.")
