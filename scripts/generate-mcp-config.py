#!/usr/bin/env python3
"""Print llama-server's MCP configuration for an Ax3l installation."""

import argparse
import json
from pathlib import Path


def configuration(app: Path) -> dict:
    app = app.resolve()
    return {"mcpServers": {"snakelab": {
        "command": str(app / ".venv/bin/python"),
        "args": ["-m", "ax3l.app.snakelab.tools"],
        "cwd": str(app),
        "env": {"PYTHONPATH": str(app), "PYTHONDONTWRITEBYTECODE": "1"},
    }}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(configuration(args.app), indent=2))
