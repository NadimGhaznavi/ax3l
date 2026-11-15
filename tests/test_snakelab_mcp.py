"""Private MCP sessions bind identifiers and forward choices through real ZMQ."""

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from ax3l.app.Prompt import Prompt
from ax3l.app.snakelab.ToolConversation import converse
from ax3l.interface.SnakeLabTools import SnakeLabTools
from ax3l.zmq.ZMQServer import ZMQServer


ROOT = Path(__file__).resolve().parents[1]


class SnakeLabMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_unbound_sessions_discover_tools_but_cannot_submit(self):
        entry = StdioServerParameters(command=sys.executable, args=['-m', 'ax3l.app.snakelab.tools'],
                                      cwd=str(ROOT), env={'PYTHONPATH': str(ROOT), 'PYTHONDONTWRITEBYTECODE': '1'})
        async with Client(entry, read_timeout_seconds=10) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            self.assertEqual(set(tools), {'submit_single_value', 'submit_pair_values', 'submit_simulation_summary'})
            for name, arguments in (('submit_single_value', {'value': 240}),
                                    ('submit_pair_values', {'value_1': .91, 'value_2': .95}),
                                    ('submit_simulation_summary', {'summary': 'Scores rose. Loss fell.'})):
                self.assertEqual(set(tools[name].input_schema['properties']), set(arguments))
                self.assertTrue((await client.call_tool(name, arguments)).is_error)

    async def test_single_choices_bind_the_draft_and_parameter_outside_model_arguments(self):
        requests = []
        def handle(message):
            requests.append(message)
            return {'status': 'ok', 'draft_id': 'draft', 'phase': 'choosing'}
        with ZMQServer('tcp://127.0.0.1:*', handle) as server:
            async with SnakeLabTools(server.endpoint, 'hidden_size', draft_id='draft') as tools:
                self.assertEqual(set(tools.definition['function']['parameters']['properties']), {'value'})
                self.assertIn('without running a simulation', tools.definition['function']['description'])
                self.assertEqual((await tools.submit({'value': 240}))['draft_id'], 'draft')
                self.assertEqual(requests[-1].payload, {'draft_id': 'draft', 'parameter': 'hidden_size', 'value': 240})
                for value in ('240', True):
                    with self.assertRaises(RuntimeError):
                        await tools.submit({'value': value})
                self.assertEqual(len(requests), 1)
                self.assertTrue((await tools._client.call_tool('submit_simulation_summary', {'summary': 'A. B.'})).is_error)

    async def test_all_pair_assignments_forward_two_values_and_private_draft_id(self):
        requests = []
        response = {'status': 'rejected', 'code': 'invalid_value'}
        def handle(message):
            requests.append(message)
            return response
        with ZMQServer('tcp://127.0.0.1:*', handle) as server:
            for pair, values in (('epsilon_pair', (.91, .95)), ('reward_pair', (.25, -.5)),
                                 ('epsilon_nice_pair', (.01, 40))):
                async with SnakeLabTools(server.endpoint, pair, draft_id='draft') as tools:
                    self.assertEqual(tools.definition['function']['name'], 'submit_pair_values')
                    arguments = dict(zip(('value_1', 'value_2'), values))
                    self.assertEqual(await tools.submit(arguments), response)
                    self.assertEqual(requests[-1].payload, {'draft_id': 'draft', 'pair': pair, **arguments})
                    count = len(requests)
                    with self.assertRaises(RuntimeError):
                        await tools.submit({'value_1': True, 'value_2': values[1]})
                    self.assertEqual(len(requests), count)
                    self.assertTrue((await tools._client.call_tool('submit_single_value', {'value': 240})).is_error)

    async def test_summary_session_binds_run_and_accepts_only_text(self):
        requests = []
        def handle(message):
            requests.append(message)
            return {'status': 'ok', 'analysis_run_id': 'bound-run'}
        with ZMQServer('tcp://127.0.0.1:*', handle) as server:
            async with SnakeLabTools(server.endpoint, 'simulation_summary', run_id='bound-run') as tools:
                self.assertEqual(set(tools.definition['function']['parameters']['properties']), {'summary'})
                text = 'Scores rose during training. Most games ended at walls.'
                self.assertEqual((await tools.submit({'summary': text}))['analysis_run_id'], 'bound-run')
                self.assertEqual(requests[-1].method, 'submit_simulation_summary')
                self.assertEqual(requests[-1].payload, {'run_id': 'bound-run', 'summary': text})
                with self.assertRaises(RuntimeError):
                    await tools.submit({'summary': 123})
                self.assertEqual(len(requests), 1)

    async def test_conversation_dispatches_the_discovered_tool_and_returns_its_result(self):
        def handle(message):
            return {'status': 'ok', 'draft_id': message.payload['draft_id'], 'phase': 'choosing'}
        llm = Mock(url='fixture')
        llm.complete.return_value = (200, '', json.dumps({'choices': [{'message': {
            'role': 'assistant', 'tool_calls': [{'id': 'choice', 'type': 'function', 'function': {
                'name': 'submit_single_value', 'arguments': '{"value":240}'}}]}}]}).encode())
        with ZMQServer('tcp://127.0.0.1:*', handle) as server:
            async with SnakeLabTools(server.endpoint, 'hidden_size', draft_id='draft') as tools:
                result = await converse(llm, Path('/tmp'), Mock(), tools, [Prompt('Choose a value')])
                self.assertEqual(result, {'status': 'ok', 'draft_id': 'draft', 'phase': 'choosing'})
