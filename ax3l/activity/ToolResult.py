"""Present a recorded tool response, translating JSON into readable Markdown."""

import json
import re

from markdown_it import MarkdownIt

from ax3l.activity.JsonMarkdown import json_markdown
from ax3l.constants.DEventCategory import DEventCategory as Events


def tool_result_html(event: dict) -> str:
    if event["name"] == Events.Tool.FAILED:
        text = event["content"]
    else:
        result = json.loads(event["content"])
        if "page" in result:
            text = result["page"]
        elif result["status"] == "rejected":
            text = "Rejected.\n\n" + result["prompt"]["content"]
        else:
            text = json.dumps(result, ensure_ascii=False)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        text = re.sub(r"^```json[ \t]*\n(.*?)^```[ \t]*$",
                      lambda match: json_markdown(json.loads(match[1])), text,
                      flags=re.MULTILINE | re.DOTALL)
    else:
        text = json_markdown(data)
    return MarkdownIt("commonmark", {"html": False}).enable("table").disable("image").render(text)
