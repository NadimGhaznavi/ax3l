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

    async def test_mcp_uses_ax3l_validation_and_submission_handler(self):
        from unittest.mock import Mock, patch
        from ax3l.app.snakelab.GenerateDefaultConfig import GenerateDefaultConfig
        from ax3l.server.ToolHandler import handle_tool
        from ax3l.zmq.ZMQServer import ZMQServer

        baseline = GenerateDefaultConfig().run()
        with patch('ax3l.server.ToolHandler.DbMgr'), patch(
            'ax3l.app.snakelab.SubmitSingleValueHandler.EventLogDb'
        ) as events, patch('ax3l.app.snakelab.SubmitSingleValueHandler.SnakeLab') as snake:
            events.return_value.current_golden_config.return_value = {'process_id': 'golden-run'}
            snake.return_value.get_config.return_value = baseline
            snake.return_value.is_config_unique.side_effect = [False, True, False]
            snake.return_value.submit_simulation.return_value = 'submitted-run'
            with ZMQServer('tcp://127.0.0.1:*', handle_tool) as server:
                entry = configuration(ROOT)['mcpServers']['snakelab']
                entry['env']['AX3L_ZMQ_ENDPOINT'] = server.endpoint
                async with Client(StdioServerParameters(**entry), read_timeout_seconds=10) as client:
                    for value, expected in [(0.2, 'invalid_value'),
                                            (baseline['training']['learning_rate'], 'duplicate_config'),
                                            (0.004, 'duplicate_config'), (0.003, 'ok'), (0.003, 'duplicate_config')]:
                        result = await client.call_tool('submit_single_value', {'parameter': 'learning_rate', 'value': value})
                        payload = json.loads(result.content[0].text)
                        self.assertEqual(payload.get('code', payload['status']), expected)
                        if expected != 'ok':
                            self.assertEqual(payload['prompt']['role'], 'user')
                    snake.return_value.submit_simulation.assert_called_once()
                    submitted = snake.return_value.submit_simulation.call_args.args[0]
                    self.assertEqual(submitted['training']['learning_rate'], 0.003)
                    self.assertEqual(baseline['training']['learning_rate'], 0.0021)

    async def test_conversation_dispatches_discovered_tool_through_mcp_and_zmq(self):
        from unittest.mock import Mock
        from ax3l.app.Prompt import Prompt
        from ax3l.app.snakelab.ToolConversation import converse
        from ax3l.interface.SnakeLabTools import SnakeLabTools
        from ax3l.zmq.ZMQServer import ZMQServer
        requests = []
        run_id = 'f6e72cb3-9bcf-4669-b368-a17c656bad79'
        def handle(message):
            requests.append(message.payload)
            return {'status': 'ok', 'run_id': run_id}
        llm = Mock(url='fixture')
        llm.complete.return_value = (200, '', json.dumps({'choices': [{'message': {
            'role': 'assistant', 'content': None, 'tool_calls': [{
                'type': 'function', 'id': 'call-1', 'function': {
                    'name': 'submit_single_value',
                    'arguments': '{"parameter":"hidden_size","value":240}'}}]}}]}).encode())
        with ZMQServer('tcp://127.0.0.1:*', handle) as server:
            async with SnakeLabTools(server.endpoint) as tools:
                self.assertEqual(set(tools.definition['function']['parameters']['properties']['parameter']['enum']),
                                 {'hidden_size', 'sequence_length', 'batch_size', 'learning_rate', 'gamma'})
                self.assertEqual(await converse(llm, Path('/tmp'), Mock(), tools, [Prompt('Choose one parameter')]), run_id)
        self.assertEqual(requests, [{'parameter': 'hidden_size', 'value': 240}])
        payload = json.loads(llm.complete.call_args.args[0])
        self.assertEqual(payload['tools'][0]['function']['name'], 'submit_single_value')
