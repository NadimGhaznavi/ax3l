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
            tools = {tool.name: tool for tool in result.tools}
            self.assertEqual(set(tools), {"submit_single_value", "submit_pair_values"})
            schema = tools["submit_single_value"].input_schema
            self.assertEqual(set(schema["required"]), {"value"})
            self.assertEqual(set(schema["properties"]), {"value"})
            result = await client.call_tool("submit_single_value", {"value": 16})
            self.assertTrue(result.is_error)
            schema = tools["submit_pair_values"].input_schema
            self.assertEqual(set(schema["required"]), {"value_1", "value_2"})
            self.assertEqual(set(schema["properties"]), {"value_1", "value_2"})
            result = await client.call_tool("submit_pair_values", {"value_1": .96, "value_2": .97})
            self.assertTrue(result.is_error)

    async def test_pair_tools_bind_assignments_and_forward_replies(self):
        from ax3l.interface.SnakeLabTools import SnakeLabTools
        from ax3l.zmq.ZMQServer import ZMQServer

        requests = []
        reply = {"status": "ok", "run_id": "accepted-run"}

        def handle(message):
            requests.append(message)
            return reply

        with ZMQServer("tcp://127.0.0.1:*", handle) as server:
            for pair, names, values in (
                ("epsilon_pair", ("epsilon.initial", "epsilon.decay"), (.96, .97)),
                ("reward_pair", ("game.rewards.closer_to_food", "game.rewards.further_from_food"), (2, -2)),
            ):
                async with SnakeLabTools(server.endpoint, pair) as tools:
                    definition = tools.definition["function"]
                    self.assertEqual(definition["name"], "submit_pair_values")
                    self.assertEqual(set(definition["parameters"]["properties"]), {"value_1", "value_2"})
                    for index, name in enumerate(names, start=1):
                        self.assertIn(f"value_{index} = {name}", definition["description"])
                    self.assertIn("minimum", definition["description"])
                    arguments = dict(zip(("value_1", "value_2"), values))
                    for response in ({"status": "ok", "run_id": "accepted-run"},
                                     {"status": "rejected", "code": "invalid_value"}):
                        reply = response
                        self.assertEqual(await tools.submit(arguments), response)
                        self.assertEqual(requests[-1].method, "submit_pair_values")
                        self.assertEqual(requests[-1].payload, {"pair": pair, **arguments})
                    count = len(requests)
                    for invalid in ({"value_1": "2", "value_2": values[1]},
                                    {"value_1": values[0], "value_2": True},
                                    {"value_1": values[0]}):
                        with self.assertRaises(RuntimeError):
                            await tools.submit(invalid)
                    self.assertEqual(len(requests), count)
                    result = await tools._client.call_tool("submit_single_value", {"value": 2})
                    self.assertTrue(result.is_error)

    async def test_mcp_forwards_proposals_and_returns_ax3l_replies(self):
        entry = configuration(ROOT)["mcpServers"]["snakelab"]
        with zmq.asyncio.Context() as context:
            with context.socket(zmq.REP) as server:
                server.setsockopt(zmq.LINGER, 0)
                port = server.bind_to_random_port("tcp://127.0.0.1")
                entry["env"]["AX3L_ZMQ_ENDPOINT"] = f"tcp://127.0.0.1:{port}"
                entry["env"]["AX3L_CONVERSATION_PARAMETER"] = "learning_rate"
                async with Client(StdioServerParameters(**entry), read_timeout_seconds=10) as client:
                    cases = [
                        ({"parameter": "learning_rate", "value": 0.003}, {"status": "ok", "run_id": "accepted-run"}),
                        ({"parameter": "learning_rate", "value": -4}, {"status": "rejected", "reason": "Invalid value"}),
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
                        _, result = await asyncio.gather(exchange(), client.call_tool("submit_single_value", {"value": proposal["value"]}))
                        self.assertFalse(result.is_error)
                        self.assertEqual(json.loads(result.content[0].text), reply)
                    for value in ("0.003", True):
                        result = await client.call_tool("submit_single_value", {"value": value})
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
                entry['env']['AX3L_CONVERSATION_PARAMETER'] = 'learning_rate'
                async with Client(StdioServerParameters(**entry), read_timeout_seconds=10) as client:
                    for value, expected in [(0.2, 'invalid_value'),
                                            (baseline['training']['learning_rate'], 'duplicate_config'),
                                            (0.004, 'duplicate_config'), (0.003, 'ok'), (0.003, 'duplicate_config')]:
                        result = await client.call_tool('submit_single_value', {'value': value})
                        payload = json.loads(result.content[0].text)
                        self.assertEqual(payload.get('code', payload['status']), expected)
                        if expected != 'ok':
                            self.assertEqual(payload['prompt']['role'], 'user')
                    snake.return_value.submit_simulation.assert_called_once()
                    submitted = snake.return_value.submit_simulation.call_args.args[0]
                    self.assertEqual(submitted['training']['learning_rate'], 0.003)
                    self.assertEqual(baseline['training']['learning_rate'], 0.0021)

    async def test_pair_mcp_reaches_ax3l_validation_and_submission(self):
        from copy import deepcopy
        from unittest.mock import patch
        from ax3l.app.snakelab.GenerateDefaultConfig import GenerateDefaultConfig
        from ax3l.interface.SnakeLabTools import SnakeLabTools
        from ax3l.server.ToolHandler import handle_tool
        from ax3l.zmq.ZMQServer import ZMQServer

        baseline = GenerateDefaultConfig().run()
        shared = 'ax3l.app.snakelab.SubmitSingleValueHandler'
        with patch('ax3l.server.ToolHandler.DbMgr'), patch(shared + '.EventLogDb') as events, patch(shared + '.SnakeLab') as snake:
            events.return_value.current_golden_config.return_value = {'process_id': 'golden-run'}
            snake.return_value.get_config.return_value = baseline
            snake.return_value.is_config_unique.return_value = True
            snake.return_value.submit_simulation.return_value = 'submitted-run'
            with ZMQServer('tcp://127.0.0.1:*', handle_tool) as server:
                for pair, values, invalid in (
                    ('epsilon_pair', (.91, .95), (.91, 1.5)),
                    ('reward_pair', (3, -3), (3, -3.5)),
                ):
                    async with SnakeLabTools(server.endpoint, pair) as tools:
                        snake.return_value.reset_mock()
                        snake.return_value.is_config_unique.return_value = True
                        result = await tools.submit(dict(zip(('value_1', 'value_2'), invalid)))
                        self.assertEqual(result['code'], 'invalid_value')
                        self.assertEqual(result['prompt']['role'], 'user')
                        snake.return_value.submit_simulation.assert_not_called()
                        arguments = dict(zip(('value_1', 'value_2'), values))
                        result = await tools.submit(arguments)
                        self.assertEqual(result, {'status': 'ok', 'run_id': 'submitted-run'})
                        expected = deepcopy(baseline)
                        if pair == 'epsilon_pair':
                            expected['epsilon'].update(initial=values[0], decay=values[1])
                        else:
                            expected['game']['rewards'].update(closer_to_food=values[0], further_from_food=values[1])
                        snake.return_value.submit_simulation.assert_called_once_with(expected)
                        snake.return_value.is_config_unique.return_value = False
                        result = await tools.submit(arguments)
                        self.assertEqual(result['code'], 'duplicate_config')
                        snake.return_value.submit_simulation.assert_called_once()

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
                    'arguments': '{"value":240}'}}]}}]}).encode())
        with ZMQServer('tcp://127.0.0.1:*', handle) as server:
            for parameter in ('hidden_size', 'sequence_length'):
                async with SnakeLabTools(server.endpoint, parameter) as tools:
                    self.assertEqual(set(tools.definition['function']['parameters']['properties']), {'value'})
                    description = tools.definition['function']['description']
                    self.assertIn(parameter, description)
                    self.assertIn('multipleOf', description)
                    for other in {'hidden_size', 'sequence_length', 'batch_size', 'learning_rate', 'gamma'} - {parameter}:
                        self.assertNotIn(other, description)
                    self.assertEqual(await converse(llm, Path('/tmp'), Mock(), tools, [Prompt('Choose a value')]), run_id)
        self.assertEqual(requests, [{'parameter': 'hidden_size', 'value': 240},
                                    {'parameter': 'sequence_length', 'value': 240}])
        payload = json.loads(llm.complete.call_args.args[0])
        self.assertEqual(payload['tools'][0]['function']['name'], 'submit_single_value')
