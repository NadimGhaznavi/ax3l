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
from ax3l.constants.DSimulationAnalysis import DSimulationAnalysis
from ax3l.constants.DChoice import CHOICE_LABELS
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
        analysis_tasks = []
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
                if tool == 'submit_simulation_summary':
                    self_test.assertEqual(request['messages'][0]['content'][1]['type'], 'image_url')
                    content = request['messages'][0]['content'][0]['text']
                    label = next(label for label in DSimulationAnalysis.SECTIONS.values()
                                 if f'Task: {label} ' in content)
                    pages = [message['content'] for message in request['messages'] if message['role'] == 'tool']
                    paths = ['/run/config', '/run/rules']
                    if len(pages) < len(paths):
                        tool, arguments = 'data_tool', dict(url=paths[len(pages)])
                    else:
                        run_id = candidate_id if calls else baseline_id
                        self_test.assertEqual(json.loads(pages[0])['config'], results[run_id]['config'])
                        rules = json.loads(pages[1])['parameters']
                        self_test.assertEqual(rules['training.learning_rate']['maximum'], .005)
                        self_test.assertEqual(rules['epsilon_nice.steps']['maximum'], 50)
                        self_test.assertNotIn(run_id.split('-')[0], '\n'.join(pages))
                        analysis_tasks.append(label)
                        arguments = {'summary': f'{label} observation. Try training.learning_rate=0.001 next.'}
                else:
                    self_test.assertEqual(calls, [])
                    content = request['messages'][1]['content']
                    parameter = next(name for name in PARAMETER_ORDER if f'Choose {CHOICE_LABELS[name]}.' in content)
                    pages = [message['content'] for message in request['messages'] if message['role'] == 'tool']
                    paths = ['/draft', '/', '/latest/notes']
                    if len(pages) < len(paths):
                        tool, arguments = 'data_tool', {'url': paths[len(pages)]}
                    else:
                        notes = json.loads(pages[-1])
                        for label in DSimulationAnalysis.SECTIONS.values():
                            self_test.assertIn(f'{label}: {label} observation.', notes['summary'])
                        draft_data = json.loads(pages[0].split('```json\n', 1)[1].split('\n```', 1)[0])
                        if selections:
                            self_test.assertEqual(draft_data['choices']['hidden_size'],
                                                  dict(state='chosen', values=dict(hidden_size=240)))
                        self_test.assertNotIn(baseline_id.split('-')[0], '\n'.join(pages))
                        selections.append(parameter)
                        value = values[parameter]
                        arguments = ({'value_1': value[0], 'value_2': value[1]} if isinstance(value, tuple)
                                     else {'value': value})
                return 200, '', json.dumps({'choices': [{'message': {
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
                patch('ax3l.app.snakelab.SubmitSimulationSummaryHandler.SnakeLab', return_value=snake), \
                patch('ax3l.interface.SimulationData.SnakeLab', return_value=snake), \
                patch('ax3l.app.snakelab.AnalyzeRun.render_analysis', return_value=b'png'), \
                patch.object(ExperimentDb, 'save_draft', save_and_stop), \
                ZMQServer('tcp://127.0.0.1:*', handle_tool) as server:
            with self.assertRaises(asyncio.CancelledError):
                await optimize(InferenceFixture(), Path('/tmp'), db, server.endpoint)
        self.assertEqual(len(calls), 1)
        self.assertEqual(analysis_tasks, list(DSimulationAnalysis.SECTIONS.values()) * 2)
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
        self.assertIn('Try training.learning_rate=0.001 next.', saved.summary)
        rows = db.query("SELECT name, COUNT(*) AS n FROM events WHERE event_id>%s AND name IN ('simulation_analyzed','simulation_analysis_progress','simulation_submitted','configuration_compared') GROUP BY name", (first_event,))
        self.assertEqual({row['name']: row['n'] for row in rows},
                         {'simulation_analyzed': 2, 'simulation_analysis_progress': 4,
                          'simulation_submitted': 1, 'configuration_compared': 1})
