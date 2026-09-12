"""Remind the LLM to submit its choice through the tool."""

from ax3l.app.Prompt import Prompt


class UseTool(Prompt):
    def __init__(self):
        super().__init__("Please submit using the submit_single_value tool")
