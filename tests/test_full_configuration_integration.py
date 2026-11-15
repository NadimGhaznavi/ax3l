"""Exercise the optimizer, MCP subprocesses, ZMQ handlers, and real MariaDB."""

import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from ax3l.app.ConfigurationLog import ConfigurationLog
from ax3l.app.DbMgr import DbMgr
from ax3l.app.EventLogDb import EventLogDb
from ax3l.app.snakelab.ExperimentDb import ExperimentDb
from ax3l.app.snakelab.SnakeLabLoop import optimize
from ax3l.entities.ConfigurationDraft import PARAMETER_ORDER
from ax3l.constants.DChoice import CHOICE_CHARTS, CHOICE_LABELS
from ax3l.interface.SimulationConfiguration import SimulationConfiguration
from ax3l.server.ToolHandler import handle_tool
from ax3l.zmq.ZMQServer import ZMQServer


@unittest.skipUnless(os.environ.get('AX3L_TEST_DB') == '1', 'requires disposable MariaDB test database')
class FullConfigurationIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_complete_cycle_uses_bound_tools_and_submits_once_after_every_choice(self):
        self.assertEqual(os.environ['DB_NAME'], 'ax3l_test')
        db = DbMgr()
        self.addCleanup(db.close)
        first_event = db.query('SELECT COALESCE(MAX(event_id), 0) AS id FROM events')[0]['id']
        def cleanup():
            db.execute('UPDATE events SET parent_event_id=NULL WHERE event_id>%s', (first_event,))
            db.execute('DELETE FROM events WHERE event_id>%s', (first_event,))
        self.addCleanup(cleanup)
        baseline_id, candidate_id = str(uuid4()), str(uuid4())
        config = SimulationConfiguration.defaults()
        results = {baseline_id: dict(status='completed', high_score=10, config=config)}
        calls = []
        selections = []
        chart_choices = []
        values = dict(hidden_size=240, sequence_length=12, batch_size=26,
                      learning_rate=.003, gamma=.97, epsilon_pair=(.91, .95),
                      reward_pair=(.25, -.5), epsilon_nice_pair=(.01, 40))

        class SimulationFixture:
            def is_simulation_running(self):
                return False
            def get_run_result(self, run_id):
                return deepcopy(results[run_id])
            def get_latest_completed_run_id(self):
                return candidate_id if candidate_id in results else baseline_id
            def get_all_time_best_run_id(self):
                return self.get_latest_completed_run_id()
            def get_num_sims(self):
                return len(results)
            def get_analysis_episodes(self, run_id):
                return [dict(episode=index, score=results[run_id]['high_score'] if index == 10 else index - 1,
                             steps=20 + index, epsilon=.5 if index < 5 else 0,
                             loss=None if index == 1 else 1 / index,
                             outcome='wall' if index <= 3 else 'snake',
                             epsilon_injections=1, epsilon_nice_injections=2)
                        for index in range(1, 11)]
            def is_config_unique(self, candidate):
                return all(candidate != result['config'] for result in results.values())
            def submit_simulation(self, candidate):
                self_test.assertEqual(selections, PARAMETER_ORDER)
                calls.append(deepcopy(candidate))
                results[candidate_id] = dict(status='completed', high_score=12, config=deepcopy(candidate))
                return candidate_id
            def get_simulation_status(self, run_id):
                return 'completed'

        self_test = self
        snake = SimulationFixture()

        class InferenceFixture:
            url = 'fixture://local-inference'
            def complete(self, payload):
                request = json.loads(payload)
                tool = request['tools'][0]['function']['name']
                self_test.assertIn(tool, ('submit_single_value', 'submit_pair_values'))
                self_test.assertEqual(calls, [])
                content = request['messages'][0]['content']
                text = content[0]['text'] if isinstance(content, list) else content
                parameter = next(name for name in PARAMETER_ORDER if f'Choose {CHOICE_LABELS[name]}.' in text)
                evidence = json.loads(text.split('```json\n')[1].split('\n```')[0])
                self_test.assertEqual(evidence['reference_runs']['golden']['high_score'], 10)
                pages = [message['content'] for message in request['messages'] if message['role'] == 'tool']
                if len(pages) == 0 and parameter == 'learning_rate':
                    tool, arguments = 'data_tool', {'url': '/golden/activity'}
                else:
                    if parameter in CHOICE_CHARTS:
                        self_test.assertEqual([part['type'] for part in content], ['text', 'image_url'])
                        chart_choices.append(parameter)
                    else:
                        self_test.assertIsInstance(content, str)
                    if pages:
                        self_test.assertEqual(json.loads(pages[0])['episodes_with_loss'], 9)
                    self_test.assertNotIn(baseline_id.split('-')[0], text)
                    selections.append(parameter)
                    value = values[parameter]
                    arguments = ({'value_1': value[0], 'value_2': value[1]} if isinstance(value, tuple)
                                 else {'value': value})
                return 200, '', json.dumps({'usage': {'prompt_tokens': 123, 'completion_tokens': 7},
                    'choices': [{'message': {
                    'role': 'assistant', 'content': None, 'tool_calls': [{
                        'id': str(uuid4()), 'type': 'function', 'function': {
                            'name': tool, 'arguments': json.dumps(arguments)}}]}}]}).encode()

        ConfigurationLog(db).golden_config_created(baseline_id, reason='Test baseline.',
            experiment_score={'score': 10, 'seed': config['seed'], 'simulations': 1})
        original_save = ExperimentDb.save_draft
        def save_and_stop(experiments, draft):
            original_save(experiments, draft)
            if draft.phase == 'completed':
                raise asyncio.CancelledError()

        with patch('ax3l.app.snakelab.SnakeLabLoop.SnakeLab', return_value=snake), \
                patch('ax3l.app.snakelab.SubmitSingleValueHandler.SnakeLab', return_value=snake), \
                patch('ax3l.interface.SimulationData.SnakeLab', return_value=snake), \
                patch('ax3l.app.snakelab.SnakeLabLoop.render_analysis', return_value=b'png'), \
                patch.object(ExperimentDb, 'save_draft', save_and_stop), \
                ZMQServer('tcp://127.0.0.1:*', handle_tool) as server:
            with self.assertRaises(asyncio.CancelledError):
                await optimize(InferenceFixture(), Path('/tmp'), db, server.endpoint)
        self.assertEqual(len(calls), 1)
        self.assertEqual(chart_choices, list(CHOICE_CHARTS))
        self.assertEqual(calls[0]['model']['hidden_size'], 240)
        self.assertEqual(calls[0]['training']['learning_rate'], .003)
        self.assertEqual(calls[0]['epsilon_nice'], {'probability': .01, 'steps': 40})
        self.assertEqual(EventLogDb(db).current_golden_config()['process_id'], candidate_id)
        draft = ExperimentDb(db).draft()
        self.assertEqual(draft.phase, 'completed')
        self.assertEqual(draft.run_id, candidate_id)
        saved = ExperimentDb(db).analysis(candidate_id)
        self.assertEqual(saved.metrics['termination_reasons']['wall'], {'count': 3, 'percent': 30})
        self.assertEqual(saved.metrics['termination_reasons']['snake'], {'count': 7, 'percent': 70})
        self.assertIsNone(saved.summary)
        events = ExperimentDb(db).choice_events(draft.draft_id)
        self.assertEqual(sum(event['name'] == 'llm_request_started' for event in events), 9)
        self.assertEqual(sum(bool(event['has_image']) for event in events), 3)
        replies = [json.loads(event['detail']) for event in events if event['name'] == 'reply_received']
        self.assertEqual(replies, [{'prompt_tokens': 123, 'completion_tokens': 7}] * 9)
        self.assertNotIn('data:image/png', json.dumps(events, default=str))
        rows = db.query("SELECT name, COUNT(*) AS n FROM events WHERE event_id>%s AND name IN ('simulation_analyzed','simulation_analysis_progress','simulation_submitted','configuration_compared') GROUP BY name", (first_event,))
        self.assertEqual({row['name']: row['n'] for row in rows},
                         {'simulation_analyzed': 2,
                          'simulation_submitted': 1, 'configuration_compared': 1})
