"""Translate HTTP requests into reporting queries and HTML responses."""

from http.server import BaseHTTPRequestHandler
import logging
import re
from time import perf_counter
from urllib.parse import parse_qs, urlsplit

from ax3l.app.reporting.Reports import Reports
from ax3l.constants.DEventCategory import DEventCategory as Events
from ax3l.constants.DReportMgr import DReportMgr
from ax3l.interface.SimulationGifStore import SimulationGifStore
from ax3l.presentation.reporting.ReportRenderer import ReportRenderer


class ReportRequestError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class ReportHandler(BaseHTTPRequestHandler):
    reports: Reports
    renderer: ReportRenderer
    gifs: SimulationGifStore
    timeout = DReportMgr.REQUEST_TIMEOUT_SECONDS
    _run_id = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"

    def send_error(self, code, message=None, explain=None):
        try:
            super().send_error(code, message, explain)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    @staticmethod
    def _found(value, message: str):
        if value is None:
            raise ReportRequestError(404, message)
        return value

    def do_GET(self):
        started = perf_counter()
        try:
            body, content_type = self._response()
        except ReportRequestError as error:
            self.send_error(error.status, error.message)
            return
        except Exception:
            logging.exception("Unable to load report %s", self.path)
            self.send_error(500, "Unable to load report")
            return
        finally:
            elapsed = perf_counter() - started
            if elapsed >= 1:
                logging.warning("Report %s took %.3f seconds", self.path, elapsed)
        try:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _response(self) -> tuple[bytes, str]:
        path = urlsplit(self.path).path
        query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
        if path == "/health":
            return b'{"status":"ok","service":"reporting-server","mode":"events"}', "application/json"
        if match := re.fullmatch(rf"/simulation-gifs/(v[0-9]+-[0-9]+ms)/({self._run_id})\.gif", path):
            version, run_id = match.groups()
            file = self.gifs.path(run_id)
            if version != self.gifs.directory.name or not file.is_file():
                raise ReportRequestError(404, "Animation not found")
            return file.read_bytes(), "image/gif"
        if path == "/":
            body = self.renderer.recent(self.reports.recent())
        elif match := re.fullmatch(r"/tool-results/([0-9]{1,20})", path):
            event = self._found(self.reports.event(int(match[1])), "Tool result not found")
            if event["category"] != Events.Tool.CATEGORY or event["name"] not in (Events.Tool.COMPLETED, Events.Tool.FAILED):
                raise ReportRequestError(404, "Tool result not found")
            body = self.renderer.tool_result(event)
        elif match := re.fullmatch(r"/events/([0-9]{1,20})(/reason)?", path):
            event = self._found(self.reports.event(int(match[1])), "Event not found")
            if (event["category"], event["name"]) not in (
                    (Events.Conversation.CATEGORY, Events.Conversation.RESPONSE),
                    (Events.Conversation.CATEGORY, Events.Conversation.PROMPT),
                    (Events.LLM.CATEGORY, Events.LLM.RESPONSE_CAPTURED)):
                raise ReportRequestError(404, "Event not found")
            body = self._found(self.renderer.event(event, reason=bool(match[2]), preview=query.get("preview") == ["1"]),
                               "Reason not found")
        elif path == "/golden-configurations":
            body = self.renderer.golden_configurations(self.reports.golden_configurations())
        elif path == "/simulation-metrics":
            sizes = query.get("bucket_size", [str(DReportMgr.SIMULATION_BUCKET_SIZE)])
            try:
                if len(sizes) != 1 or int(sizes[0]) < 1:
                    raise ValueError
                bucket_size = int(sizes[0])
            except ValueError as error:
                raise ReportRequestError(400, "Bucket size must be a positive integer") from error
            body = self.renderer.simulation_metrics(self.reports.simulation_metrics(), bucket_size)
        elif path == "/experiment-highscores":
            body = self.renderer.experiment_highscores(**self.reports.experiment_highscores())
        elif path == "/score-distribution":
            body = self.renderer.score_distribution(self.reports.score_distribution())
        elif match := re.fullmatch(rf"/simulations/({self._run_id})(/config)?", path):
            run_id = match[1]
            if match[2]:
                config = self._found(self.reports.configuration(run_id), "Simulation not found")
                body = self.renderer.configuration(run_id, config)
            else:
                data = self._found(self.reports.simulation(run_id), "Simulation not found")
                body = self.renderer.simulation(data)
        else:
            raise ReportRequestError(404, "Not Found")
        return body, "text/html; charset=utf-8"
