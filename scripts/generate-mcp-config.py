#!/usr/bin/env python3
"""Print llama-server's MCP configuration for an Ax3l installation."""

import argparse
import json
from pathlib import Path


def configuration(app: Path, zmq_endpoint: str | None = None) -> dict:
    app = app.resolve()
    config = {"mcpServers": {"snakelab": {
        "command": str(app / ".venv/bin/python"),
        "args": ["-m", "ax3l.app.snakelab.tools"],
        "cwd": str(app),
        "env": {"PYTHONPATH": str(app), "PYTHONDONTWRITEBYTECODE": "1"},
    }}}
    if zmq_endpoint is not None:
        config["mcpServers"]["snakelab"]["env"]["AX3L_ZMQ_ENDPOINT"] = zmq_endpoint
    return config


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--zmq-endpoint")
    args = parser.parse_args()
    print(json.dumps(configuration(args.app, args.zmq_endpoint), indent=2))
