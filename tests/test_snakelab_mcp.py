"""Private MCP sessions bind identifiers and forward choices through real ZMQ."""

import json
from copy import deepcopy
from pathlib import Path
import sys
from threading import Event
from time import monotonic
import unittest
from unittest.mock import Mock, patch

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from ax3l.app.Prompt import Prompt
from ax3l.app.snakelab.ToolConversation import converse, DecisionTimeExpired
from ax3l.app.snakelab.RunSimulationHandler import RunSimulationHandler
from ax3l.app.snakelab.SelectParameterHandler import SelectParameterHandler
from ax3l.app.snakelab.prompts.ConfigurationNextStep import ConfigurationNextStep
from ax3l.constants.DChoice import REVISION_PARAMETER
from ax3l.entities.ConfigurationDraft import ConfigurationDraft, PARAMETER_ORDER
from ax3l.entities.SimulationAnalysis import SimulationAnalysis
from ax3l.interface.SimulationConfiguration import SimulationConfiguration
from ax3l.interface.SnakeLabTools import SnakeLabTools
from ax3l.zmq.ZMQServer import ZMQServer


ROOT = Path(__file__).resolve().parents[1]


class SnakeLabMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_grace_expiry_cancels_a_read_without_submitting_a_choice(self):
        release = Event()
        requests = []

        def handle(message):
            requests.append(message)
            release.wait()
            return dict(status='ok', page='Late data.')

        llm = Mock(url='fixture')
        llm.complete.return_value = (200, '', json.dumps({'choices': [{'message': dict(role='assistant', tool_calls=[
            dict(id='data', type='function', function=dict(name='kb_tool', arguments='{"url":"/draft"}'))])}]}).encode())
        with ZMQServer('tcp://127.0.0.1:*', handle) as server:
            async with SnakeLabTools(server.endpoint, REVISION_PARAMETER, draft_id='draft') as tools:
                now = monotonic()
                try:
                    with self.assertRaises(DecisionTimeExpired):
                        await converse(llm, Path('/tmp'), Mock(), tools, [Prompt('Decide.')],
                                       conversation_deadline=now + .2)
                finally:
                    release.set()
        self.assertEqual([request.method for request in requests], ['read_simulation_data'])

    async def test_unbound_sessions_discover_tools_but_cannot_submit(self):
        entry = StdioServerParameters(command=sys.executable, args=['-m', 'ax3l.app.snakelab.tools'],
                                      cwd=str(ROOT), env={'PYTHONPATH': str(ROOT), 'PYTHONDONTWRITEBYTECODE': '1'})
        async with Client(entry, read_timeout_seconds=10) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            self.assertEqual(set(tools), {'submit_single_value', 'submit_pair_values', 'select_parameter',
                                         'run_simulation', 'request_seed_change', 'submit_simulation_summary',
                                         'kb_tool'})
            for name, arguments in (('submit_single_value', {'value': 240}),
                                    ('submit_pair_values', {'value_1': .91, 'value_2': .95}),
                                    ('select_parameter', {'parameter': 'layers'}),
                                    ('run_simulation', {}),
                                    ('request_seed_change', {}),
                                    ('submit_simulation_summary', {'summary': 'Scores rose. Loss fell.'})):
                self.assertEqual(set(tools[name].input_schema['properties']), set(arguments))
                self.assertTrue((await client.call_tool(name, arguments)).is_error)
            self.assertEqual(set(tools['kb_tool'].input_schema['properties']), {'url'})
            self.assertFalse((await client.call_tool('kb_tool', {'url': '/'})).is_error)
            self.assertTrue((await client.call_tool('kb_tool', {'url': '/draft'})).is_error)

    async def test_revision_session_uses_prompt_choices_and_keeps_the_draft_private(self):
        requests = []

        def handle(message):
            requests.append(message)
            if message.method == 'read_simulation_data':
                return dict(status='ok', page='Saved draft values.')
            return dict(status='ok', draft_id='private-draft', phase='choosing')

        with ZMQServer('tcp://127.0.0.1:*', handle) as server:
            async with SnakeLabTools(server.endpoint, REVISION_PARAMETER, draft_id='private-draft') as tools:
                self.assertEqual([definition['function']['name'] for definition in tools.definitions],
                                 ['select_parameter', 'run_simulation', 'kb_tool'])
                self.assertEqual(set(tools.definition['function']['parameters']['properties']), {'parameter'})
                description = tools.definition['function']['description']
                self.assertIn('exact key from settings', description)
                self.assertIn('Selecting seed immediately saves the next unused seed', description)
                for name in (parameter for parameter in PARAMETER_ORDER if parameter != 'seed'):
                    self.assertNotIn(name, description)
                self.assertNotIn('private-draft', json.dumps(tools.definitions))
                self.assertEqual((await tools.read(dict(url='/draft')))['page'], 'Saved draft values.')
                self.assertEqual((await tools.submit(dict(parameter='layers')))['phase'], 'choosing')
                self.assertEqual(requests[-1].method, 'select_parameter')
                self.assertEqual(requests[-1].payload, dict(draft_id='private-draft', parameter='layers'))
                for arguments in (dict(parameter=True), dict(parameter=2)):
                    with self.assertRaises(RuntimeError):
                        await tools.submit(arguments)
                self.assertTrue((await tools._client.call_tool('submit_single_value', dict(value=72))).is_error)
                self.assertTrue((await tools._client.call_tool('request_seed_change', {})).is_error)
                self.assertEqual(len(requests), 2)
            async with SnakeLabTools(server.endpoint, 'layers', draft_id='private-draft') as tools:
                self.assertTrue((await tools._client.call_tool('select_parameter', dict(parameter='gamma'))).is_error)
                self.assertEqual(len(requests), 2)

    async def test_parameter_selection_can_research_data_before_selecting_a_setting(self):
        requests = []

        def handle(message):
            requests.append(message)
            if message.method == 'read_simulation_data':
                return dict(status='ok', page='Measured scores and current settings.')
            return dict(status='ok', phase='choosing')

        def reply(name, arguments):
            return 200, '', json.dumps({'choices': [{'message': dict(role='assistant', tool_calls=[
                dict(id=name, type='function', function=dict(name=name, arguments=json.dumps(arguments)))])}]}).encode()

        llm = Mock(url='fixture')
        llm.complete.side_effect = [reply('kb_tool', dict(url='/')),
                                   reply('kb_tool', dict(url='/guides/model')),
                                   reply('kb_tool', dict(url='/golden/scores')),
                                   reply('select_parameter', dict(parameter='gamma'))]
        with ZMQServer('tcp://127.0.0.1:*', handle) as server:
            async with SnakeLabTools(server.endpoint, REVISION_PARAMETER, draft_id='private-draft') as tools:
                self.assertEqual((await converse(llm, Path('/tmp'), Mock(), tools, [Prompt('Research a setting.')],
                                                 conversation_deadline=monotonic() + 300))['phase'],
                                 'choosing')
        self.assertEqual([request.method for request in requests],
                         ['read_simulation_data', 'read_simulation_data', 'select_parameter'])
        payload = json.loads(llm.complete.call_args.args[0])
        pages = [message['content'] for message in payload['messages'] if message['role'] == 'tool']
        self.assertEqual(len(pages), 3)
        self.assertIn('[Open lab reference](/guides)', pages[0])
        self.assertIn('24-value feature vector', pages[1])
        self.assertEqual([message['content'] for message in payload['messages'] if message['role'] == 'user'],
                         ['Research a setting.'])
        self.assertNotIn('private-draft', json.dumps(payload))

    async def test_unique_candidate_can_research_then_run_or_select_another_setting(self):
        requests = []

        def handle(message):
            requests.append(message)
            if message.method == 'read_simulation_data':
                return dict(status='ok', page='Current draft values.')
            return dict(status='ok', phase='ready' if message.method == 'run_simulation' else 'choosing')

        def reply(name, arguments):
            return 200, '', json.dumps({'choices': [{'message': dict(role='assistant', tool_calls=[
                dict(id=name, type='function', function=dict(name=name, arguments=json.dumps(arguments)))])}]}).encode()

        with ZMQServer('tcp://127.0.0.1:*', handle) as server:
            async with SnakeLabTools(server.endpoint, REVISION_PARAMETER,
                                     draft_id='private-draft') as tools:
                self.assertEqual([definition['function']['name'] for definition in tools.definitions],
                                 ['select_parameter', 'run_simulation', 'kb_tool'])
                for action, arguments, phase in (('run_simulation', {}, 'ready'),
                                                  ('select_parameter', dict(parameter='layers'), 'choosing')):
                    llm = Mock(url='fixture')
                    llm.complete.side_effect = [reply('kb_tool', dict(url='/draft')), reply(action, arguments)]
                    self.assertEqual((await converse(llm, Path('/tmp'), Mock(), tools, [Prompt('Choose next step.')]))['phase'],
                                     phase)
                    self.assertEqual(requests[-1].method, action)
                    self.assertEqual(requests[-1].payload, dict(draft_id='private-draft', **arguments))

    async def test_duplicate_run_returns_to_the_screen_and_preserves_research(self):
        requests, db, store, snake = [], Mock(), Mock(), Mock()
        draft = ConfigurationDraft('private-draft', 'gold', {}, SimulationConfiguration.defaults())
        original_config = deepcopy(draft.config)
        store.draft.return_value = draft
        snake.is_config_unique.return_value = False
        snake.available_parameters.side_effect = lambda config, parameters: parameters

        def reply(name, arguments):
            return 200, '', json.dumps({'choices': [{'message': dict(role='assistant', tool_calls=[
                dict(id=name, type='function', function=dict(name=name, arguments=json.dumps(arguments)))])}]}).encode()

        with patch('ax3l.app.snakelab.RunSimulationHandler.ExperimentDb', return_value=store), \
                patch('ax3l.app.snakelab.SelectParameterHandler.ExperimentDb', return_value=store), \
                patch('ax3l.app.snakelab.SubmitSingleValueHandler.SnakeLab', return_value=snake):
            run, select = RunSimulationHandler(db), SelectParameterHandler(db)

            def handle(message):
                requests.append(message)
                return (run if message.method == 'run_simulation' else select).submit(message.payload)

            golden = SimulationAnalysis('gold', deepcopy(draft.config), dict(high_score=20), None)
            references = dict.fromkeys(('best', 'golden', 'latest'), golden)
            screen = ConfigurationNextStep(draft, PARAMETER_ORDER, references)
            llm = Mock(url='fixture')
            llm.complete.side_effect = [reply('kb_tool', dict(url='/definitions/golden.md')),
                                       reply('run_simulation', {}),
                                       reply('select_parameter', dict(parameter='gamma'))]
            with ZMQServer('tcp://127.0.0.1:*', handle) as server:
                async with SnakeLabTools(server.endpoint, REVISION_PARAMETER, draft_id=draft.draft_id) as tools:
                    result = await converse(llm, Path('/tmp'), db, tools, [screen],
                                            conversation_deadline=monotonic() + 300)
        self.assertEqual(result['phase'], 'choosing')
        self.assertEqual([request.method for request in requests],
                         ['run_simulation', 'select_parameter'])
        messages = json.loads(llm.complete.call_args.args[0])['messages']
        self.assertTrue(any("Don't show your reasoning in the prompt." in (message.get('content') or '')
                            for message in messages if message['role'] == 'tool'))
        user_messages = [message['content'] for message in messages if message['role'] == 'user']
        self.assertEqual(user_messages[:2], [screen.to_md(), screen.to_md()])
        feedback = [message['content'] for message in messages if message['role'] == 'user'][-1]
        self.assertIn('configuration already exists', feedback)
        self.assertTrue(feedback.endswith(screen.to_md()))
        self.assertNotIn('private-draft', json.dumps(messages))
        self.assertEqual(draft.config, original_config)
        self.assertEqual(draft.selections, [])
        self.assertEqual(draft.parameter, 'gamma')
        store.save_draft.assert_called_once_with(draft)
        snake.is_config_unique.assert_called_once_with(original_config)
        snake.submit_simulation.assert_not_called()

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
                ('empty', 2, 'at least -2; at most 2'),
                ('snake', -2.5, 'at least -20; at most 0'),
                ('wall', -5, 'at least -20; at most 0'),
            ):
                async with SnakeLabTools(server.endpoint, parameter, draft_id='draft') as tools:
                    self.assertIn('run_simulation', [definition['function']['name'] for definition in tools.definitions])
                    self.assertEqual(set(tools.definition['function']['parameters']['properties']), {'value'})
                    self.assertIn('Save a changed value in the draft.', tools.definition['function']['description'])
                    self.assertIn(rule, tools.definition['function']['description'])
                    self.assertEqual((await tools.submit({'value': value}))['draft_id'], 'draft')
                    self.assertEqual(requests[-1].payload, {'draft_id': 'draft', 'parameter': parameter, 'value': value})
                    count = len(requests)
                    for invalid in (str(value), True):
                        with self.assertRaises(RuntimeError):
                            await tools.submit({'value': invalid})
                    self.assertEqual(len(requests), count)
                    self.assertTrue((await tools._client.call_tool('submit_simulation_summary', {'summary': 'A. B.'})).is_error)

    async def test_seed_conversation_researches_then_requests_a_change_with_no_model_arguments(self):
        requests = []

        def handle(message):
            requests.append(message)
            if message.method == 'read_simulation_data':
                return dict(status='ok', page='Measured reference scores.')
            return dict(status='ok', draft_id='private-draft', phase='reviewing', seed=1971)

        def reply(tool, arguments):
            return 200, '', json.dumps({'choices': [{'message': dict(role='assistant', tool_calls=[
                dict(id=str(len(arguments)) + tool, type='function',
                     function=dict(name=tool, arguments=json.dumps(arguments)))])}]}).encode()

        llm = Mock(url='fixture')
        llm.complete.side_effect = [reply('kb_tool', {'url': '/golden/scores'}),
                                   reply('request_seed_change', {'value': 99}),
                                   reply('request_seed_change', {})]
        with ZMQServer('tcp://127.0.0.1:*', handle) as server:
            async with SnakeLabTools(server.endpoint, 'seed', draft_id='private-draft') as tools:
                self.assertEqual([definition['function']['name'] for definition in tools.definitions],
                                 ['request_seed_change', 'run_simulation', 'kb_tool'])
                self.assertEqual(tools.definition['function']['parameters']['properties'], {})
                self.assertNotIn('private-draft', json.dumps(tools.definitions))
                self.assertTrue((await tools._client.call_tool('submit_single_value', {'value': 99})).is_error)
                result = await converse(llm, Path('/tmp'), Mock(), tools, [Prompt('Request a seed change.')])
        self.assertEqual(result['seed'], 1971)
        self.assertEqual([request.method for request in requests], ['read_simulation_data', 'request_seed_change'])
        self.assertEqual(requests[-1].payload, {'draft_id': 'private-draft'})
        self.assertEqual(llm.complete.call_count, 3)

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
                self.assertNotIn('run_simulation', [definition['function']['name'] for definition in tools.definitions])
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
        llm.complete.side_effect = [reply('kb_tool', {'url': '/guides'}),
                                   reply('kb_tool', {'url': '/guides/analysis/'}),
                                   reply('kb_tool', {'url': '/guides/analysis/loss'}),
                                   reply('submit_simulation_summary', {'summary': 'Recorded loss fell.'})]
        with ZMQServer('tcp://127.0.0.1:*', handle) as server:
            async with SnakeLabTools(server.endpoint, 'simulation_summary', run_id='bound-run', section='loss') as tools:
                self.assertEqual([definition['function']['name'] for definition in tools.definitions],
                                 ['submit_simulation_summary', 'kb_tool'])
                result = await converse(llm, Path('/tmp'), Mock(), tools, [Prompt('Describe loss.')])
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].payload['section'], 'loss')
        payloads = [json.loads(entry.args[0]) for entry in llm.complete.call_args_list]
        self.assertEqual(len(payloads), 4)
        pages = [message['content'] for message in payloads[-1]['messages']
                 if message['role'] == 'tool']
        self.assertIn('/guides/analysis/', pages[0])
        self.assertIn('/guides/analysis/loss', pages[1])
        self.assertIn('unrecorded, not zero', pages[2])

    async def test_reference_url_errors_allow_a_corrected_lookup_without_submitting(self):
        async with SnakeLabTools('tcp://127.0.0.1:1', 'hidden_size', draft_id='draft') as tools:
            for url in ('/guides/../../etc/passwd', '/guides/https://example.com', '/guides/missing'):
                result = await tools.read({'url': url})
                self.assertEqual(result['status'], 'rejected')
            self.assertEqual((await tools.read({'url': '/guides'}))['status'], 'ok')

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
        llm.complete.side_effect = [reply('kb_tool', {'url': '/missing'}),
                                   reply('kb_tool', {'url': '/draft'}),
                                   reply('kb_tool', {'url': '/latest/model'}),
                                   reply('submit_single_value', {'value': 240})]
        with ZMQServer('tcp://127.0.0.1:*', handle) as server:
            async with SnakeLabTools(server.endpoint, 'hidden_size', draft_id='private-draft') as tools:
                definition = next(d for d in tools.definitions if d['function']['name'] == 'kb_tool')
                self.assertEqual(set(definition['function']['parameters']['properties']), {'url'})
                self.assertIn('null means unrecorded', definition['function']['description'])
                result = await converse(llm, Path('/tmp'), Mock(), tools, [Prompt('Choose hidden size.')])
                before = len(requests)
                with self.assertRaises(RuntimeError):
                    await tools.read({'url': 123})
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
        llm.complete.side_effect = [reply('kb_tool', dict(url='/run/training')),
                                   reply('kb_tool', dict(url='/run/rules')),
                                   reply('submit_simulation_summary', dict(summary=summary))]
        with ZMQServer('tcp://127.0.0.1:*', handle) as server:
            async with SnakeLabTools(server.endpoint, 'simulation_summary', run_id='private-run', section='loss') as tools:
                definition = next(d['function'] for d in tools.definitions if d['function']['name'] == 'kb_tool')
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
                await tools.read({'url': '/run/config'})

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
