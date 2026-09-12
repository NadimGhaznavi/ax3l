import argparse
from importlib import import_module
from threading import Thread

from ax3l.interface.HealthServer import HealthServer


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Ax3l and its first simulation conversation.")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--llm-url", help="Send the first iteration to this LLM server")
    parser.add_argument("--output", default="tmp/haiku")
    args = parser.parse_args()
    mode = "first-iteration" if args.llm_url else "skeleton"
    with HealthServer().make_server("ax3l-server", args.port, mode) as server:
        if not args.llm_url:
            server.serve_forever()
            return 0
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            loop = import_module("ax3l.app.snakelab.main-loop")
            return loop.main(["--url", args.llm_url, "--output", args.output])
        finally:
            server.shutdown()
            worker.join()


if __name__ == "__main__":
    raise SystemExit(main())
