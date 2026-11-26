"""Compose the reporting application and its HTTP service."""

import argparse
from http.server import HTTPServer, ThreadingHTTPServer
from pathlib import Path

from ax3l.app.reporting.ReportBackground import ReportBackground
from ax3l.app.reporting.Reports import Reports
from ax3l.constants.DReportMgr import DReportMgr
from ax3l.interface.Network import Network
from ax3l.interface.ReportHandler import ReportHandler
from ax3l.interface.SimulationGifStore import SimulationGifStore
from ax3l.interface.SnakeLab import SnakeLab
from ax3l.presentation.reporting.ReportRenderer import ReportRenderer
from ax3l.presentation.reporting.SimulationAnimation import SimulationAnimation


def make_server(host: str, port: int, gif_directory: Path = DReportMgr.GIF_DIRECTORY,
                gif_duration_ms: int = DReportMgr.GIF_DURATION_MS) -> HTTPServer:
    if gif_duration_ms < 10:
        raise ValueError("GIF frame duration must be at least 10 ms")
    gifs = SimulationGifStore(gif_directory, SimulationAnimation.VERSION, gif_duration_ms)
    background = ReportBackground(gifs, gif_duration_ms)

    class Handler(ReportHandler):
        pass

    class ReportServer(ThreadingHTTPServer):
        def server_close(self):
            try:
                super().server_close()
            finally:
                background.close()

    try:
        Handler.reports = Reports(SnakeLab(), background, gifs)
        Handler.renderer = ReportRenderer()
        Handler.gifs = gifs
        return ReportServer((host, port), Handler)
    except BaseException:
        background.close()
        raise


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Show the application event log.")
    parser.add_argument("--port", type=int)
    parser.add_argument("--host")
    parser.add_argument("--gif-dir", type=Path, default=DReportMgr.GIF_DIRECTORY)
    parser.add_argument("--gif-duration-ms", type=int, default=DReportMgr.GIF_DURATION_MS,
                        help="Move duration in milliseconds, at least 10 (rounded to GIF ticks)")
    args = parser.parse_args(argv)
    host, port = Network.binding("report")
    host = args.host if args.host is not None else host
    port = args.port if args.port is not None else port
    with make_server(host, port, args.gif_dir, args.gif_duration_ms) as server:
        print(f"Event log: http://{host}:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
