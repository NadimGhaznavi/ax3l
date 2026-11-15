import argparse
import os
from importlib import import_module

from ax3l.interface.Configuration import Configuration
from ax3l.interface.Network import Network
from ax3l.server.ToolHandler import handle_tool
from ax3l.zmq.ZMQServer import ZMQServer


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Ax3l and its single-parameter optimization loop.")
    parser.add_argument("--llm-url", type=Configuration.validate_llamasrv_url,
                        help="Override the configured LlamaSrv base URL")
    parser.add_argument("--output", default="tmp/snakelab")
    parser.add_argument("--zmq-endpoint", default=None)
    args = parser.parse_args()
    llm_url = args.llm_url if args.llm_url is not None else Network.llamasrv_url()
    endpoint = args.zmq_endpoint if args.zmq_endpoint is not None else os.environ.get("AX3L_ZMQ_ENDPOINT")
    if endpoint is None:
        endpoint = Network.endpoint()
    with ZMQServer(endpoint, handle_tool) as tool_server:
        loop = import_module("ax3l.app.snakelab.main-loop")
        destination = tool_server.endpoint.replace("tcp://0.0.0.0:", "tcp://127.0.0.1:", 1)
        return loop.main(["--url", llm_url, "--output", args.output, "--zmq-endpoint", destination])


if __name__ == "__main__":
    raise SystemExit(main())
