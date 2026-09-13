import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import traceback

from jinja2 import Environment, FileSystemLoader, select_autoescape
import zmq

from ax3l.app.DbMgr import DbMgr
from ax3l.constants.DEventCategory import DEventCategory
from ax3l.app.EventLogDb import EventLogDb
from ax3l.activity.ReplyReport import fields, reply_content
from ax3l.activity.PromptReport import parts, summary
from ax3l.activity.ScoreDistribution import distribution
from ax3l.constants.DReportMgr import DReportMgr
from ax3l.interface.SnakeLab import SnakeLab


def make_server(host: str, port: int) -> HTTPServer:
    templates = Environment(
        loader=FileSystemLoader(Path(__file__).with_name("templates")),
        autoescape=select_autoescape(["html"]),
    )
    template = templates.get_template("events.html")
    templates.globals["event_label"] = DEventCategory.label
    templates.globals["simulation_events"] = DEventCategory.SnakeLab
    templates.globals["request_timeout_seconds"] = DReportMgr.REQUEST_TIMEOUT_SECONDS

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                body = b'{"status":"ok","service":"reporting-server","mode":"events"}'
                content_type = "application/json"
            elif self.path == "/score-distribution":
                try:
                    body = templates.get_template("score_distribution.html").render(
                        **distribution(SnakeLab().get_run_scores())
                    ).encode("utf-8")
                    content_type = "text/html; charset=utf-8"
                except Exception:
                    traceback.print_exc()
                    self.send_error(500, "Unable to load score distribution")
                    return
            elif re.fullmatch(
                r"/simulations/[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}/config",
                self.path,
            ):
                run_id = self.path.split("/")[2]
                try:
                    config = SnakeLab().get_config(run_id)
                    if config is None:
                        self.send_error(404, "Simulation not found")
                        return
                    body = (
                        templates.get_template("config.html")
                        .render(
                            run_id=run_id,
                            rows=fields(config),
                        )
                        .encode("utf-8")
                    )
                    content_type = "text/html; charset=utf-8"
                except Exception:
                    traceback.print_exc()
                    self.send_error(500, "Unable to load simulation config")
                    return
            elif self.path == "/" or re.fullmatch(r"/events/[0-9]{1,20}", self.path):
                try:
                    db = DbMgr()
                    try:
                        log = EventLogDb(db)
                        if self.path == "/":
                            events = log.recent()
                            for event in events:
                                if (
                                    event["name"] == DEventCategory.Conversation.RESPONSE
                                    and event["category"]
                                    == DEventCategory.Conversation.CATEGORY
                                ):
                                    event["reply_text"] = reply_content(
                                        json.loads(event["content"])
                                    )
                                elif (
                                    event["name"] == DEventCategory.Conversation.PROMPT
                                    and event["category"]
                                    == DEventCategory.Conversation.CATEGORY
                                ):
                                    event["prompt_text"] = summary(
                                        json.loads(event["content"])
                                    )
                            try:
                                simulation_running = SnakeLab().is_simulation_running()
                            except zmq.ZMQError:
                                snake_lab_status = "Service Unavailable"
                            else:
                                snake_lab_status = (
                                    "Running Simulation" if simulation_running else "Idle"
                                )
                            body = template.render(
                                events=events,
                                snake_lab_status=snake_lab_status,
                                high_score=SnakeLab().get_high_score(),
                                simulations_submitted=SnakeLab().get_num_sims(),
                                experiment_cycles=log.experiment_cycles(),
                            ).encode("utf-8")
                        else:
                            event = log.get(int(self.path.rsplit("/", 1)[1]))
                            if (
                                event is None
                                or event["name"]
                                not in (
                                    DEventCategory.Conversation.RESPONSE,
                                    DEventCategory.Conversation.PROMPT,
                                )
                                or event["category"]
                                != DEventCategory.Conversation.CATEGORY
                            ):
                                self.send_error(404)
                                return
                            if event["name"] == DEventCategory.Conversation.PROMPT:
                                body = (
                                    templates.get_template("prompt.html")
                                    .render(
                                        event=event,
                                        parts=parts(json.loads(event["content"])),
                                    )
                                    .encode("utf-8")
                                )
                            else:
                                response = json.loads(event["content"])
                                groups = ("choices", "usage", "timings")
                                sections = [
                                    (
                                        "Response",
                                        fields(
                                            {
                                                key: value
                                                for key, value in response.items()
                                                if key not in groups
                                            }
                                        ),
                                    )
                                ]
                                sections.extend(
                                    (key, fields(response[key], key))
                                    for key in groups
                                    if key in response
                                )
                                body = (
                                    templates.get_template("reply.html")
                                    .render(
                                        event=event,
                                        reply_text=reply_content(response),
                                        sections=sections,
                                    )
                                    .encode("utf-8")
                                )
                    finally:
                        db.close()
                    content_type = "text/html; charset=utf-8"
                except Exception:
                    traceback.print_exc()
                    self.send_error(500, "Unable to load event log")
                    return
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return HTTPServer((host, port), Handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Show the application event log.")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    with make_server(args.host, args.port) as server:
        print(f"Event log: http://{args.host}:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
