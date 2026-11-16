"""Present a recorded tool response, translating JSON into readable Markdown."""

import json

from ax3l.activity.MarkdownReport import markdown_html
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
    return markdown_html(text)
