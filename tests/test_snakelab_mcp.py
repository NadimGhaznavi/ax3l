import asyncio
import json

import zmq
import zmq.asyncio
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
            self.assertEqual([tool.name for tool in result.tools], ["submit_single_value"])
            schema = result.tools[0].input_schema
            self.assertEqual(set(schema["required"]), {"parameter", "value"})

    async def test_mcp_forwards_proposals_and_returns_ax3l_replies(self):
        entry = configuration(ROOT)["mcpServers"]["snakelab"]
        with zmq.asyncio.Context() as context:
            with context.socket(zmq.REP) as server:
                server.setsockopt(zmq.LINGER, 0)
                port = server.bind_to_random_port("tcp://127.0.0.1")
                entry["env"]["AX3L_ZMQ_ENDPOINT"] = f"tcp://127.0.0.1:{port}"
                async with Client(StdioServerParameters(**entry), read_timeout_seconds=10) as client:
                    cases = [
                        ({"parameter": "learning_rate", "value": 0.003}, {"status": "ok", "run_id": "accepted-run"}),
                        ({"parameter": "unknown_parameter", "value": -4}, {"status": "rejected", "reason": "Unknown parameter"}),
                    ]
                    for proposal, reply in cases:
                        async def exchange():
                            request = await asyncio.wait_for(server.recv_json(), timeout=5)
                            self.assertEqual(request, {
                                "protocol_version": 1, "sender": "mcp-snakelab", "target": "snakelab",
                                "method": "submit_single_value", "payload": proposal,
                            })
                            await server.send_json({
                                "protocol_version": 1, "sender": "ax3l", "target": "mcp-snakelab",
                                "method": "submit_single_value", "payload": reply,
                            })
                        _, result = await asyncio.gather(exchange(), client.call_tool("submit_single_value", proposal))
                        self.assertFalse(result.is_error)
                        self.assertEqual(json.loads(result.content[0].text), reply)
                    for value in ("0.003", True):
                        result = await client.call_tool("submit_single_value", {"parameter": "learning_rate", "value": value})
                        self.assertTrue(result.is_error)
                    self.assertEqual(await server.poll(timeout=50), 0)
