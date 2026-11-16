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
            self.assertEqual(set(tools), {'submit_single_value', 'submit_pair_values', 'submit_simulation_summary', 'kb_tool', 'data_tool'})
            for name, arguments in (('submit_single_value', {'value': 240}),
                                    ('submit_pair_values', {'value_1': .91, 'value_2': .95}),
                                    ('submit_simulation_summary', {'summary': 'Scores rose. Loss fell.'})):
                self.assertEqual(set(tools[name].input_schema['properties']), set(arguments))
                self.assertTrue((await client.call_tool(name, arguments)).is_error)
            self.assertEqual(set(tools['data_tool'].input_schema['properties']), {'url'})
            self.assertTrue((await client.call_tool('data_tool', {'url': '/'})).is_error)

    async def test_single_choices_bind_the_draft_and_parameter_outside_model_arguments(self):
        requests = []
        def handle(message):
            requests.append(message)
            return {'status': 'ok', 'draft_id': 'draft', 'phase': 'choosing'}
        with ZMQServer('tcp://127.0.0.1:*', handle) as server:
            for parameter, value, rule in (
                ('hidden_size', 96, 'at least 32; at most 128; multiple of 8'),
                ('layers', 3, 'one of 1, 2, 3'),
                ('dropout', .02, 'one of 0.0, 0.01, 0.02'),
            ):
                async with SnakeLabTools(server.endpoint, parameter, draft_id='draft') as tools:
                    self.assertEqual(set(tools.definition['function']['parameters']['properties']), {'value'})
                    self.assertIn('without running a simulation', tools.definition['function']['description'])
                    self.assertIn(rule, tools.definition['function']['description'])
                    self.assertEqual((await tools.submit({'value': value}))['draft_id'], 'draft')
                    self.assertEqual(requests[-1].payload, {'draft_id': 'draft', 'parameter': parameter, 'value': value})
                    count = len(requests)
                    for invalid in (str(value), True):
                        with self.assertRaises(RuntimeError):
                            await tools.submit({'value': invalid})
                    self.assertEqual(len(requests), count)
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
                    if pair == 'epsilon_nice_pair':
                        description = tools.definition['function']['description']
                        self.assertIn('start chance: number; above 0; at most 0.1.', description)
                        self.assertIn('moves per detour: whole number; at least 1; at most 40.', description)
                    arguments = dict(zip(('value_1', 'value_2'), values))
                    self.assertEqual(await tools.submit(arguments), response)
                    self.assertEqual(requests[-1].payload, {'draft_id': 'draft', 'pair': pair, **arguments})
                    count = len(requests)
                    with self.assertRaises(RuntimeError):
                        await tools.submit({'value_1': True, 'value_2': values[1]})
                    self.assertEqual(len(requests), count)
                    self.assertTrue((await tools._client.call_tool('submit_single_value', {'value': 240})).is_error)

    async def test_summary_session_binds_run_and_section_and_accepts_only_text(self):
        requests = []
        def handle(message):
            requests.append(message)
            return {'status': 'ok', 'analysis_run_id': 'bound-run'}
        with ZMQServer('tcp://127.0.0.1:*', handle) as server:
            async with SnakeLabTools(server.endpoint, 'simulation_summary', run_id='bound-run', section='loss') as tools:
                self.assertEqual(set(tools.definition['function']['parameters']['properties']), {'summary'})
                text = 'Scores rose during training. Most games ended at walls.'
                self.assertEqual((await tools.submit({'summary': text}))['analysis_run_id'], 'bound-run')
                self.assertEqual(requests[-1].method, 'submit_simulation_summary')
                self.assertEqual(requests[-1].payload, {'run_id': 'bound-run', 'section': 'loss', 'summary': text})
                with self.assertRaises(RuntimeError):
                    await tools.submit({'summary': 123})
                self.assertEqual(len(requests), 1)

    async def test_reference_drill_down_returns_pages_without_submitting_and_then_finishes(self):
        requests = []
        def handle(message):
            requests.append(message)
            return {'status': 'ok', 'analysis_run_id': 'bound-run'}
        def reply(name, arguments):
            return 200, '', json.dumps({'choices': [{'message': {
                'role': 'assistant', 'tool_calls': [{'id': str(len(arguments)) + name,
                'type': 'function', 'function': {'name': name, 'arguments': json.dumps(arguments)}}]}}]}).encode()
        llm = Mock(url='fixture')
        llm.complete.side_effect = [reply('kb_tool', {'url': '/'}),
                                   reply('kb_tool', {'url': '/analysis/'}),
                                   reply('kb_tool', {'url': '/analysis/loss'}),
                                   reply('submit_simulation_summary', {'summary': 'Recorded loss fell.'})]
        with ZMQServer('tcp://127.0.0.1:*', handle) as server:
            async with SnakeLabTools(server.endpoint, 'simulation_summary', run_id='bound-run', section='loss') as tools:
                self.assertEqual([definition['function']['name'] for definition in tools.definitions],
                                 ['submit_simulation_summary', 'kb_tool', 'data_tool'])
                result = await converse(llm, Path('/tmp'), Mock(), tools, [Prompt('Describe loss.')])
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].payload['section'], 'loss')
        payloads = [json.loads(entry.args[0]) for entry in llm.complete.call_args_list]
        self.assertEqual(len(payloads), 4)
        pages = [message['content'] for message in payloads[-1]['messages']
                 if message['role'] == 'tool']
        self.assertIn('/analysis/', pages[0])
        self.assertIn('/analysis/loss', pages[1])
        self.assertIn('unrecorded, not zero', pages[2])

    async def test_reference_url_errors_allow_a_corrected_lookup_without_submitting(self):
        async with SnakeLabTools('tcp://127.0.0.1:1', 'hidden_size', draft_id='draft') as tools:
            for url in ('/../../etc/passwd', 'https://example.com', '/missing'):
                result = await tools.reference({'url': url})
                self.assertEqual(result['status'], 'rejected')
            self.assertEqual((await tools.reference({'url': '/'}))['status'], 'ok')

    async def test_data_drill_down_binds_the_draft_and_only_submission_finishes(self):
        requests = []
        model_json = json.dumps(dict(scope='latest', seed=1970, model=dict(hidden_size=224, dropout=0.1)))
        def handle(message):
            requests.append(message)
            if message.method == 'read_simulation_data':
                if message.payload['url'] == '/missing':
                    return {'status': 'rejected', 'reason': 'Unknown data page.', 'source_name': 'SimulationData',
                            'prompt': {'role': 'user', 'content': 'Unknown data page. Read /.'}}
                return {'status': 'ok', 'page': (model_json if message.payload['url'] == '/latest/model'
                                                else f"Page {message.payload['url']}")}
            return {'status': 'ok', 'draft_id': 'private-draft'}
        def reply(name, arguments):
            return 200, '', json.dumps({'choices': [{'message': {
                'role': 'assistant', 'tool_calls': [{'id': name + str(len(arguments)),
                'type': 'function', 'function': {'name': name, 'arguments': json.dumps(arguments)}}]}}]}).encode()
        llm = Mock(url='fixture')
        llm.complete.side_effect = [reply('data_tool', {'url': '/missing'}),
                                   reply('data_tool', {'url': '/draft'}),
                                   reply('data_tool', {'url': '/latest/model'}),
                                   reply('submit_single_value', {'value': 240})]
        with ZMQServer('tcp://127.0.0.1:*', handle) as server:
            async with SnakeLabTools(server.endpoint, 'hidden_size', draft_id='private-draft') as tools:
                definition = next(d for d in tools.definitions if d['function']['name'] == 'data_tool')
                self.assertEqual(set(definition['function']['parameters']['properties']), {'url'})
                self.assertIn('Data payloads are JSON', definition['function']['description'])
                result = await converse(llm, Path('/tmp'), Mock(), tools, [Prompt('Choose hidden size.')])
                before = len(requests)
                with self.assertRaises(RuntimeError):
                    await tools.data({'url': 123})
                self.assertEqual(len(requests), before)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual([r.method for r in requests], ['read_simulation_data'] * 3 + ['submit_single_value'])
        self.assertEqual(requests[1].payload, {'draft_id': 'private-draft', 'url': '/draft'})
        payloads = [json.loads(call.args[0]) for call in llm.complete.call_args_list]
        tool_content = [m['content'] for m in payloads[-1]['messages'] if m['role'] == 'tool']
        self.assertEqual(tool_content, ['Rejected.', 'Page /draft', model_json])
        self.assertEqual(json.loads(tool_content[-1])['model']['hidden_size'], 224)
        feedback = [m['content'] for m in payloads[-1]['messages'] if m['role'] == 'user']
        self.assertEqual(feedback, ['Choose hidden size.', 'Unknown data page. Read /.'])
        self.assertNotIn('private-draft', json.dumps(payloads))

    async def test_image_analysis_can_read_its_bound_run_settings_and_recommend_a_value(self):
        requests = []
        settings = json.dumps(dict(scope='run', seed=1970, training=dict(learning_rate=.002)))
        rules = json.dumps(dict(parameters={'training.learning_rate': dict(type='number', minimum=.0005, maximum=.005)}))
        summary = 'Loss spiked late; try training.learning_rate=0.001 next.'
        def handle(message):
            requests.append(message)
            if message.method == 'read_analysis_data':
                return dict(status='ok', page=settings if message.payload['url'] == '/run/training' else rules)
            return dict(status='ok', analysis_run_id='private-run')
        def reply(name, arguments):
            return 200, '', json.dumps({'choices': [{'message': {
                'role': 'assistant', 'tool_calls': [{'id': name, 'type': 'function', 'function': {
                    'name': name, 'arguments': json.dumps(arguments)}}]}}]}).encode()
        llm = Mock(url='fixture')
        llm.complete.side_effect = [reply('data_tool', dict(url='/run/training')),
                                   reply('data_tool', dict(url='/run/rules')),
                                   reply('submit_simulation_summary', dict(summary=summary))]
        with ZMQServer('tcp://127.0.0.1:*', handle) as server:
            async with SnakeLabTools(server.endpoint, 'simulation_summary', run_id='private-run', section='loss') as tools:
                definition = next(d['function'] for d in tools.definitions if d['function']['name'] == 'data_tool')
                self.assertEqual(set(definition['parameters']['properties']), {'url'})
                self.assertIn('settings that produced this chart', definition['description'])
                result = await converse(llm, Path('/tmp'), Mock(), tools, [Prompt('Analyze this image.')])
                self.assertTrue((await tools._client.call_tool('submit_single_value', dict(value=.001))).is_error)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual([request.method for request in requests], ['read_analysis_data'] * 2 + ['submit_simulation_summary'])
        self.assertEqual(requests[0].payload, dict(run_id='private-run', url='/run/training'))
        self.assertEqual(requests[-1].payload, dict(run_id='private-run', section='loss', summary=summary))
        payload = json.loads(llm.complete.call_args.args[0])
        self.assertEqual([m['content'] for m in payload['messages'] if m['role'] == 'tool'], [settings, rules])
        self.assertNotIn('private-run', json.dumps(payload))

    async def test_summary_session_without_section_cannot_submit(self):
        async with SnakeLabTools('tcp://127.0.0.1:1', 'simulation_summary', run_id='bound-run') as tools:
            with self.assertRaises(RuntimeError):
                await tools.submit({'summary': 'Loss fell.'})
            with self.assertRaises(RuntimeError):
                await tools.data({'url': '/run/config'})

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
