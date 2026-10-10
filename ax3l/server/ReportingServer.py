import argparse
import json
import re
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import traceback
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from jinja2 import Environment, FileSystemLoader, select_autoescape
import zmq

from ax3l.app.DbMgr import DbMgr
from ax3l.app.ReportBackground import ReportBackground
from ax3l.constants.DEventCategory import DEventCategory
from ax3l.app.EventLogDb import EventLogDb
from ax3l.activity.ReplyReport import fields, reply_content, reasoning_content
from ax3l.activity.PromptReport import parts, summary
from ax3l.activity.ScoreDistribution import distribution
from ax3l.activity.ExperimentHighscores import highscores
from ax3l.activity.GoldenConfigurations import parameter_change
from ax3l.activity.SimulationBoard import board_svg
from ax3l.activity.SimulationAnimation import SimulationAnimation
from ax3l.interface.SimulationGifStore import SimulationGifStore
from ax3l.activity.SimulationMetrics import metrics
from ax3l.constants.DReportMgr import DReportMgr
from ax3l.constants.DLabel import FIELD_TO_LABEL_MAP
from ax3l.interface.SnakeLab import SnakeLab


def make_server(host: str, port: int, gif_directory: Path = DReportMgr.GIF_DIRECTORY,
                gif_duration_ms: int = DReportMgr.GIF_DURATION_MS) -> HTTPServer:
    if gif_duration_ms < 10 or gif_duration_ms % 10:
        raise ValueError("GIF frame duration must be a positive multiple of 10 ms")
    gifs = SimulationGifStore(gif_directory, SimulationAnimation.VERSION, gif_duration_ms)
    background = ReportBackground(gifs, gif_duration_ms)

    def animation_url(run_id: str) -> str | None:
        if not background.animation_ready(run_id):
            return None
        return f"/simulation-gifs/{gifs.directory.name}/{UUID(run_id)}.gif"

    templates = Environment(
        loader=FileSystemLoader(Path(__file__).with_name("templates")),
        autoescape=select_autoescape(["html"]),
    )
    templates.globals["field_labels"] = FIELD_TO_LABEL_MAP
    template = templates.get_template("events.html")
    templates.globals["event_label"] = DEventCategory.label
    templates.globals["event_choices"] = {
        category.CATEGORY: sorted(set(category.LABELS.values()))
        for category in DEventCategory.ALL
    }
    templates.globals["prompt_label"] = DEventCategory.Conversation.LABELS[
        DEventCategory.Conversation.PROMPT
    ]
    templates.globals["simulation_events"] = DEventCategory.SnakeLab
    templates.globals["request_timeout_seconds"] = DReportMgr.REQUEST_TIMEOUT_SECONDS

    class Handler(BaseHTTPRequestHandler):
        def send_error(self, code, message=None, explain=None):
            try:
                super().send_error(code, message, explain)
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True

        def _send_page(self, body: bytes, content_type: str):
            try:
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                # The browser can cancel a refresh or leave before the page arrives.
                self.close_connection = True

        def do_GET(self):
            if self.path == "/health":
                body = b'{"status":"ok","service":"reporting-server","mode":"events"}'
                content_type = "application/json"
            elif re.fullmatch(
                r"/simulation-gifs/v[0-9]+-[0-9]+ms/[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\.gif",
                self.path,
            ):
                _, _, version, filename = self.path.split("/")
                path = gifs.path(filename[:-4])
                if version != gifs.directory.name or not path.is_file():
                    self.send_error(404, "Animation not found")
                    return
                body = path.read_bytes()
                content_type = "image/gif"
            elif self.path == "/golden-configurations":
                try:
                    db = DbMgr()
                    try:
                        configs = EventLogDb(db).golden_configurations()
                    finally:
                        db.close()
                    for config in configs:
                        config["has_reason"] = bool(reasoning_content(config.pop("response", None)))
                        config["change"] = parameter_change(config.get("decision"), config.get("parameter"))
                    body = templates.get_template("golden_configurations.html").render(
                        configs=configs
                    ).encode("utf-8")
                    content_type = "text/html; charset=utf-8"
                except Exception:
                    traceback.print_exc()
                    self.send_error(500, "Unable to load golden configurations")
                    return
            elif urlsplit(self.path).path == "/simulation-metrics":
                sizes = parse_qs(urlsplit(self.path).query, keep_blank_values=True).get(
                    "bucket_size", [str(DReportMgr.SIMULATION_BUCKET_SIZE)])
                try:
                    if len(sizes) != 1:
                        raise ValueError
                    bucket_size = int(sizes[0])
                    if bucket_size < 1:
                        raise ValueError
                except ValueError:
                    self.send_error(400, "Bucket size must be a positive integer")
                    return
                try:
                    db = DbMgr()
                    try:
                        history = EventLogDb(db).simulation_metrics()
                    finally:
                        db.close()
                    body = templates.get_template("simulation_metrics.html").render(
                        **metrics(history, bucket_size)
                    ).encode("utf-8")
                    content_type = "text/html; charset=utf-8"
                except Exception:
                    traceback.print_exc()
                    self.send_error(500, "Unable to load simulation metrics")
                    return
            elif self.path == "/experiment-highscores":
                try:
                    db = DbMgr()
                    try:
                        history = EventLogDb(db).experiment_highscores()
                    finally:
                        db.close()
                    body = templates.get_template("experiment_highscores.html").render(
                        **highscores(history, SnakeLab().get_num_sims())
                    ).encode("utf-8")
                    content_type = "text/html; charset=utf-8"
                except Exception:
                    traceback.print_exc()
                    self.send_error(500, "Unable to load experiment highscores")
                    return
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
                r"/simulations/[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}",
                self.path,
            ):
                try:
                    run_id = self.path.split("/")[2]
                    run = SnakeLab().get_run_summary(run_id)
                    if run is None:
                        self.send_error(404, "Simulation not found")
                        return
                    body = templates.get_template("simulation_run.html").render(
                        run=run, board_gif_url=animation_url(run_id),
                        board_svg=board_svg(run.get("high_score_snapshot"))
                    ).encode("utf-8")
                    content_type = "text/html; charset=utf-8"
                except Exception:
                    traceback.print_exc()
                    self.send_error(500, "Unable to load simulation run")
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
            elif self.path == "/" or re.fullmatch(r"/events/[0-9]{1,20}(?:/reason)?", self.path):
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
                            golden = log.current_golden_config()
                            current_run = (
                                SnakeLab().get_run_summary(golden["process_id"])
                                if golden else None
                            )
                            body = template.render(
                                hostname=socket.gethostname(),
                                events=events,
                                snake_lab_status=snake_lab_status,
                                high_score=current_run["high_score"] if current_run else None,
                                all_time_high_score=SnakeLab().get_high_score(),
                                current_board_svg=board_svg(current_run.get("high_score_snapshot")) if current_run else None,
                                current_board_gif_url=animation_url(golden["process_id"]) if current_run else None,
                                simulations_submitted=SnakeLab().get_num_sims(),
                                experiment_cycles=log.experiment_cycles(),
                                **background.episode_totals(),
                            ).encode("utf-8")
                        else:
                            reason_page = self.path.endswith("/reason")
                            event = log.get(int(self.path.split("/")[2]))
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
                            if reason_page:
                                reason = reasoning_content(event["content"])
                                if event["name"] != DEventCategory.Conversation.RESPONSE or not reason:
                                    self.send_error(404, "Reason not found")
                                    return
                                body = templates.get_template("reply.html").render(
                                    event=event, reply_text=reason, sections=[],
                                    page_title=f"Reason #{event['event_id']}",
                                    message_title="Reason", back_url="/golden-configurations",
                                    back_label="Back to golden configurations",
                                ).encode("utf-8")
                            elif event["name"] == DEventCategory.Conversation.PROMPT:
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
            self._send_page(body, content_type)

    class ReportServer(HTTPServer):
        def server_close(self):
            try:
                super().server_close()
            finally:
                background.close()

    return ReportServer((host, port), Handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Show the application event log.")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--gif-dir", type=Path, default=DReportMgr.GIF_DIRECTORY)
    parser.add_argument("--gif-duration-ms", type=int, default=DReportMgr.GIF_DURATION_MS,
                        help="Frame duration in milliseconds, a positive multiple of 10")
    args = parser.parse_args()
    with make_server(args.host, args.port, args.gif_dir, args.gif_duration_ms) as server:
        print(f"Event log: http://{args.host}:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
