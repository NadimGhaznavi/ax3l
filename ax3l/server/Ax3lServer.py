import argparse
import os
from importlib import import_module
from threading import Event

from ax3l.constants.DAx3l import DAx3l
from ax3l.server.ToolHandler import handle_tool
from ax3l.zmq.ZMQServer import ZMQServer


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Ax3l and its single-parameter optimization loop.")
    parser.add_argument("--llm-url", help="Use this LLM server for optimization")
    parser.add_argument("--output", default="tmp/snakelab")
    parser.add_argument("--zmq-endpoint", default=os.environ.get("AX3L_ZMQ_ENDPOINT", DAx3l.ZMQ_ENDPOINT))
    args = parser.parse_args()
    with ZMQServer(args.zmq_endpoint, handle_tool) as tool_server:
        if not args.llm_url:
            try:
                Event().wait()
            except KeyboardInterrupt:
                return 130
        loop = import_module("ax3l.app.snakelab.main-loop")
        return loop.main(["--url", args.llm_url, "--output", args.output, "--zmq-endpoint", tool_server.endpoint])


if __name__ == "__main__":
    raise SystemExit(main())
