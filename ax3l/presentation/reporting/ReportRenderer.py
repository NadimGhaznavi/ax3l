"""Build HTML reports and keep template configuration beside its assets."""

import json
from pathlib import Path
import socket

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ax3l.activity.ExperimentHighscores import highscores
from ax3l.activity.ScoreDistribution import distribution
from ax3l.activity.SimulationMetrics import metrics
from ax3l.constants.DAx3l import DAx3l
from ax3l.constants.DEventCategory import DEventCategory as Events
from ax3l.constants.DLabel import FIELD_TO_LABEL_MAP
from ax3l.constants.DReportMgr import DReportMgr
from ax3l.presentation.reporting.ExperimentStatus import experiment_sections, experiment_totals
from ax3l.presentation.reporting.MarkdownReport import markdown_html
from ax3l.presentation.reporting.PromptReport import parts, summary
from ax3l.presentation.reporting.ReplyReport import fields, reply_summary, reasoning_content
from ax3l.presentation.reporting.SimulationBoard import board_svg
from ax3l.presentation.reporting.ToolResult import tool_result_html


class ReportRenderer:
    def __init__(self):
        self._templates = Environment(
            loader=FileSystemLoader(Path(__file__).with_name("templates")),
            autoescape=select_autoescape(["html"]),
        )
        self._templates.globals.update(
            field_labels=FIELD_TO_LABEL_MAP, application_version=DAx3l.VERSION,
            application_codename=DAx3l.CMDB_CODENAME, event_label=Events.label,
            event_choices={category.CATEGORY: sorted(set(category.LABELS.values()))
                           for category in Events.ALL},
            prompt_label=Events.Conversation.LABELS[Events.Conversation.PROMPT],
            simulation_events=Events.SnakeLab,
            request_timeout_seconds=DReportMgr.REQUEST_TIMEOUT_SECONDS,
        )

    def _render(self, template: str, **values) -> bytes:
        return self._templates.get_template(template).render(**values).encode("utf-8")

    def recent(self, data: dict) -> bytes:
        events = []
        for original in data["events"]:
            event = dict(original)
            if event["category"] == Events.Conversation.CATEGORY:
                if event["name"] == Events.Conversation.RESPONSE:
                    event["reply_text"] = reply_summary(event["content"])
                elif event["name"] == Events.Conversation.PROMPT:
                    event["prompt_text"] = summary(json.loads(event["content"]))
            events.append(event)
        current = data["current_run"]
        values = {key: value for key, value in data.items() if key not in ("current_run", "events", "experiment")}
        sections = experiment_sections(data["experiment"])
        return self._render("events.html", hostname=socket.gethostname(),
                            current_board_svg=board_svg(current.get("high_score_snapshot"))
                            if current else None, events=events,
                            experiment_sections=sections, experiment_totals=experiment_totals(sections), **values)

    def event(self, event: dict, *, reason: bool = False, preview: bool = False) -> bytes | None:
        if reason:
            text = reasoning_content(event["content"])
            if event["name"] != Events.Conversation.RESPONSE or not text:
                return None
            return self._render("reply.html", event=event, reply_text=text, sections=[],
                                page_title=f"Reason #{event['event_id']}", message_title="Reason",
                                back_url="/golden-configurations", back_label="Back to golden configurations",
                                preview=preview, markdown_html=markdown_html)
        if event["name"] == Events.Conversation.PROMPT:
            return self._render("prompt.html", event=event, parts=parts(json.loads(event["content"])),
                                preview=preview, markdown_html=markdown_html)
        try:
            response = json.loads(event["content"])
        except json.JSONDecodeError:
            return self._render("reply.html", event=event, reply_text=event["content"], sections=[])
        if not isinstance(response, dict):
            return self._render("reply.html", event=event, reply_text=event["content"],
                                sections=[("Response", fields(response))])
        groups = ("choices", "usage", "timings")
        sections = [("Response", fields({key: value for key, value in response.items() if key not in groups}))]
        sections.extend((key, fields(response[key], key)) for key in groups if key in response)
        return self._render("reply.html", event=event, reply_text=reply_summary(event["content"]), sections=sections)

    def tool_result(self, event: dict) -> bytes:
        return self._render("tool_result.html", event=event, result_html=tool_result_html(event))

    def golden_configurations(self, configurations: list[dict]) -> bytes:
        values = [dict(config, has_reason=bool(reasoning_content(config.get("response"))))
                  for config in configurations]
        return self._render("golden_configurations.html", configs=values)

    def simulation_metrics(self, history: list[dict], bucket_size: int) -> bytes:
        return self._render("simulation_metrics.html", **metrics(history, bucket_size))

    def experiment_highscores(self, history: list[dict], submitted: int) -> bytes:
        return self._render("experiment_highscores.html", **highscores(history, submitted))

    def score_distribution(self, scores: dict[int, int | None]) -> bytes:
        return self._render("score_distribution.html", **distribution(scores))

    def simulation(self, data: dict) -> bytes:
        return self._render("simulation_run.html", board_svg=board_svg(data["run"].get("high_score_snapshot")), **data)

    def configuration(self, run_id: str, config: dict) -> bytes:
        return self._render("config.html", run_id=run_id, rows=fields(config))
