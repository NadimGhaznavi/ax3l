"""Render captured Markdown and translate JSON sections into compact tables."""

import json
import re

from markdown_it import MarkdownIt

from ax3l.presentation.reporting.JsonMarkdown import json_markdown


def _json_block(match: re.Match) -> str:
    try:
        data = json.loads(match[1])
    except json.JSONDecodeError:
        # Captured model text can contain incomplete JSON examples.
        return match[0]
    return json_markdown(data)


def markdown_html(text: str) -> str:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        text = re.sub(r"^```json[ \t]*\n(.*?)^```[ \t]*$", _json_block, text,
                      flags=re.MULTILINE | re.DOTALL)
    else:
        text = json_markdown(data)
    markdown = MarkdownIt("commonmark", {"html": False}).enable("table").disable("image")
    validate_link = markdown.validateLink
    # Captured browser paths belong to the LLM's menu, not the reporting server.
    markdown.validateLink = lambda url: (not url.startswith("/") or url.startswith("//")) and validate_link(url)
    return markdown.render(text)
