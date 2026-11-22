"""The Markdown presentation assets used by SnakeLab conversations."""

from pathlib import Path

from ax3l.interface.MarkdownTemplates import MarkdownTemplates


templates = MarkdownTemplates(Path(__file__).resolve().parent / "templates")
