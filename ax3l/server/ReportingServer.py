import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import traceback

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ax3l.app.DbMgr import DbMgr
from ax3l.app.EventLogDb import EventLogDb
from ax3l.activity.ReplyReport import fields, reply_content
from ax3l.constants.DEventDisplay import DEventDisplay


def make_server(host: str, port: int) -> HTTPServer:
    templates = Environment(
        loader=FileSystemLoader(Path(__file__).with_name("templates")),
        autoescape=select_autoescape(["html"]),
    )
    template = templates.get_template("events.html")
    templates.globals["event_labels"] = DEventDisplay.LABELS

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                body = b'{"status":"ok","service":"reporting-server","mode":"events"}'
                content_type = "application/json"
            elif self.path == "/" or re.fullmatch(r"/events/[0-9]{1,20}", self.path):
                try:
                    db = DbMgr()
                    try:
                        log = EventLogDb(db)
                        if self.path == "/":
                            events = log.recent()
                            for event in events:
                                if event["name"] == "reply_received" and event["category"] == "Conversation":
                                    event["reply_text"] = reply_content(json.loads(event["content"]))
                            body = template.render(events=events).encode("utf-8")
                        else:
                            event = log.get(int(self.path.rsplit("/", 1)[1]))
                            if event is None or event["name"] != "reply_received" or event["category"] != "Conversation":
                                self.send_error(404)
                                return
                            response = json.loads(event["content"])
                            groups = ("choices", "usage", "timings")
                            sections = [("Response", fields({
                                key: value for key, value in response.items() if key not in groups
                            }))]
                            sections.extend((key, fields(response[key], key)) for key in groups if key in response)
                            body = templates.get_template("reply.html").render(
                                event=event, reply_text=reply_content(response), sections=sections,
                            ).encode("utf-8")
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
