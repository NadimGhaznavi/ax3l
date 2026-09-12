import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import traceback

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ax3l.app.DbMgr import DbMgr
from ax3l.app.EventLogDb import EventLogDb


def make_server(host: str, port: int) -> HTTPServer:
    templates = Environment(
        loader=FileSystemLoader(Path(__file__).with_name("templates")),
        autoescape=select_autoescape(["html"]),
    )
    template = templates.get_template("events.html")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                body = b'{"status":"ok","service":"reporting-server","mode":"events"}'
                content_type = "application/json"
            elif self.path == "/":
                try:
                    db = DbMgr()
                    try:
                        events = EventLogDb(db).recent()
                    finally:
                        db.close()
                    body = template.render(events=events).encode("utf-8")
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
