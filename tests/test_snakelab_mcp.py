import json
from pathlib import Path
import subprocess
import sys
import unittest

from mcp import Client
from mcp.client.stdio import StdioServerParameters


ROOT = Path(__file__).resolve().parents[1]


def configuration(app: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/generate-mcp-config.py"), "--app", str(app)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


class SnakeLabMCPTests(unittest.IsolatedAsyncioTestCase):
    def test_config_uses_installation_paths(self):
        app = Path("/tmp/ax3l installation")
        entry = configuration(app)["mcpServers"]["snakelab"]
        self.assertEqual(entry["command"], str(app / ".venv/bin/python"))
        self.assertEqual(entry["cwd"], str(app))
        self.assertEqual(entry["args"], ["-m", "ax3l.app.snakelab.tools"])
        self.assertEqual(entry["env"]["PYTHONPATH"], str(app))

    async def test_registered_stdio_server_initializes_and_lists_tools(self):
        entry = configuration(ROOT)["mcpServers"]["snakelab"]
        async with Client(StdioServerParameters(**entry), read_timeout_seconds=10) as client:
            result = await client.list_tools()
            self.assertEqual(result.tools, [])
