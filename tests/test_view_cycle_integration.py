"""Run the service against disposable MariaDB and local HTTP/ZeroMQ fixtures.

Requires AX3L_TEST_DB=1 and DB_NAME=ax3l_test. The database must have no
simulation source tables; this fixture creates and removes its own tables.
"""

from collections import Counter
from copy import deepcopy
import json
import os
from threading import Event
import unittest
from unittest.mock import call, patch
from uuid import uuid4

from ax3l.interface.database.DbMgr import DbMgr
from ax3l.interface.database.ExperimentDb import ExperimentDb
from ax3l.interface.database.ExperimentStatusDb import ExperimentStatusDb
from ax3l.interface.database.SnakeLabDb import CONFIGURATION_FIELDS, CONFIGURATION_COLUMNS, _config_values
from ax3l.constants.DSnakeLab import DSnakeLab
from ax3l.constants.DAx3l import DAx3l
from ax3l.entities.ExperimentState import ExperimentState
from ax3l.entities.ExperimentView import VIEWS
from ax3l.interface.SimulationConfiguration import SimulationConfiguration
from ax3l.interface.SnakeLab import SnakeLab
from ax3l.presentation.reporting.ExperimentStatus import experiment_sections
from ax3l.server.Ax3lServer import main
from view_cycle_fixtures import LocalLLM, LocalSnakeControl, episodes, requested_view


@unittest.skipUnless(os.environ.get('AX3L_TEST_DB') == '1', 'requires disposable MariaDB test database')
class ViewCycleIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ['DB_NAME'], 'ax3l_test')
        self.enterContext(patch.object(DSnakeLab, 'DATABASE', 'ax3l_test'))
        self.db = DbMgr()
        self.addCleanup(self.db.close)
        self.tables = []
        self.start_event = self.db.query('SELECT COALESCE(MAX(event_id), 0) AS id FROM events')[0]['id']
        self.addCleanup(self.clean_database)
        self.db.execute('''CREATE TABLE simulation_runs (
            id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, run_id CHAR(36) UNIQUE,
            status VARCHAR(20), high_score INT, project_version VARCHAR(64),
            started_at DATETIME(6), completed_at DATETIME(6)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci''')
        self.tables.append('simulation_runs')
        types = dict(integer='BIGINT', number='DOUBLE', string='VARCHAR(64)')
        columns = ', '.join(f'{column} {types[kind]}' for column, _, kind in CONFIGURATION_FIELDS)
        self.db.execute(f'''CREATE TABLE configurations (run_id CHAR(36) PRIMARY KEY, {columns})
            ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci''')
        self.tables.append('configurations')
        self.db.execute('''CREATE TABLE simulation_episodes (
            run_id CHAR(36), episode INT, score INT, steps INT, epsilon DOUBLE, loss DOUBLE,
            outcome VARCHAR(32), epsilon_injections INT, epsilon_nice_injections INT,
            PRIMARY KEY(run_id, episode)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci''')
        self.tables.append('simulation_episodes')
        self.scores = iter((10, 9, 12, 7))
        self.control = LocalSnakeControl(self.handle_control)
        self.addCleanup(self.control.close)
        self.model = LocalLLM()
        self.addCleanup(self.model.close)

    def clean_database(self):
        self.db.execute('UPDATE events SET parent_event_id=NULL WHERE event_id > %s', (self.start_event,))
        self.db.execute('DELETE FROM events WHERE event_id > %s', (self.start_event,))
        for table in reversed(self.tables):
            self.db.execute(f'DROP TABLE {table}')

    def handle_control(self, method, payload):
        db = DbMgr(initialize_event_tables=False)
        try:
            if method == 'simulation.active':
                return dict(run=None)
            if method == 'simulation.status':
                return dict(run_id=payload['run_id'], state='completed')
            if method != 'simulation.submit':
                raise ValueError(f'Unexpected fixture method: {method}')
            run_id = str(uuid4())
            config = payload['config']
            count = len(CONFIGURATION_FIELDS) + 1
            with db.transaction():
                db.execute('''INSERT INTO simulation_runs
                    (run_id, status, high_score, project_version, started_at, completed_at)
                    VALUES (%s, 'completed', %s, 'fixture', CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))''',
                    (run_id, next(self.scores)))
                db.execute(f'''INSERT INTO configurations (run_id, {CONFIGURATION_COLUMNS})
                    VALUES ({', '.join(['%s'] * count)})''', (run_id, *_config_values(config)))
                for row in episodes():
                    db.execute('''INSERT INTO simulation_episodes
                        (run_id, episode, score, steps, epsilon, loss, outcome, epsilon_injections,
                         epsilon_nice_injections) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                        (run_id, *[row[key] for key in ('episode', 'score', 'steps', 'epsilon', 'loss',
                                                       'outcome', 'epsilon_injections', 'epsilon_nice_injections')]))
            return dict(run_id=run_id, state='queued')
        finally:
            db.close()

    def service(self, cycles=1):
        with patch('sys.argv', ['ax3l', '--cycles', str(cycles), '--llm-url',
                                self.model.llm.url.removesuffix('/v1/chat/completions'),
                                '--zmq-endpoint', 'tcp://127.0.0.1:*']), \
                patch('ax3l.server.Ax3lServer.SnakeLab', side_effect=lambda: SnakeLab(self.control.endpoint)), \
                patch('builtins.print'):
            return main()

    def count_events(self, name):
        return self.db.query('SELECT COUNT(*) AS n FROM events WHERE name=%s AND event_id > %s',
                             (name, self.start_event))[0]['n']

    def request_steps(self):
        return [(requested_view(request), request['tools'][0]['function']['name'])
                for request in self.model.requests]

    def test_view_and_report_roll_over_across_rounds_and_service_restarts(self):
        orders = [list(VIEWS), list(reversed(VIEWS)), list(VIEWS)[1:] + list(VIEWS)[:1]]
        rounds = iter(orders)
        expected = orders[0] + orders[1] + orders[2][:1]
        self.scores = iter((10, 11, 12, 12, 13, 14, 15, 15, 16, 17))
        experiments = set()
        def next_round(names):
            names[:] = next(rounds)
        with patch('ax3l.app.experiment.ExperimentLoop.shuffle',
                   side_effect=next_round) as shuffle:
            for index, name in enumerate(expected):
                with self.subTest(cycle=index, view=name):
                    self.assertEqual(self.service(), 0)
                    state = ExperimentDb(self.db).load()
                    self.assertNotIn(state.experiment_id, experiments)
                    experiments.add(state.experiment_id)
                    self.assertEqual(state.phase, 'completed')
                    self.assertEqual(state.view_name, name)
                    self.assertEqual(state.view_index, index % 4)
                    self.assertEqual(state.order, orders[index // 4])
                    self.assertEqual(set(state.proposals), {name})
                    self.assertEqual(set(state.observations), {name})
                    self.assertEqual(state.golden_history.view, name)
                    self.assertEqual(state.failures, 0)
                    runs = self.db.query('SELECT run_id FROM simulation_runs ORDER BY id')
                    self.assertEqual(len(runs), index + 2)
                    self.assertEqual(state.reference_run_id, runs[-2]['run_id'])
                    self.assertEqual(state.golden_run_id, runs[-1]['run_id'])
                    data = ExperimentStatusDb(self.db).read()
                    data['latest_config'] = state.config
                    sections = experiment_sections(data)
                    self.assertEqual([s['id'] for s in sections],
                                     [f'selection-{name}', f'evaluation-{name}'])
                    self.assertEqual([s['status'] for s in sections], ['Saved', 'Saved'])
                    self.assertEqual(sections[1]['observations'], state.observations[name])
        self.assertEqual(shuffle.call_count, 3)
        self.assertEqual(self.request_steps(), [(name, tool) for name in expected
                         for tool in ('submit_view', 'submit_observations')])
        self.assertEqual(self.count_events('configuration_compared'), 9)
        self.assertEqual(self.count_events('proposal_accepted'), 9)

    def test_each_view_corrects_long_hypotheses_and_the_reported_observation(self):
        observation = ('Hypothesis not supported. Increasing hidden size to 128 and adding a '
                       'second layer resulted in a lower high score (29) compared to the '
                       'golden score (34). The 90th percentile chart shows the latest model '
                       'consistently underperforming the golden model. The larger '
                       'architecture did not improve navigation.')
        respond = self.model.respond
        def overlong(request):
            response = respond(request)
            if len(request['messages']) == 1:
                function = response['choices'][0]['message']['tool_calls'][0]['function']
                arguments = json.loads(function['arguments'])
                field = 'hypothesis' if function['name'] == 'submit_view' else 'observations'
                arguments[field] = 'x' * 300 if field == 'hypothesis' else observation
                function['arguments'] = json.dumps(arguments)
            return response
        self.model.respond = overlong
        self.scores = iter((10, 11, 12, 13, 14))
        with patch('ax3l.app.experiment.ExperimentLoop.shuffle', side_effect=lambda names: names.reverse()):
            self.assertEqual(self.service(cycles=4), 0)
        expected = [(name, tool) for name in reversed(VIEWS)
                    for tool in ('submit_view', 'submit_observations') for _ in range(2)]
        self.assertEqual(self.request_steps(), expected)
        for original, corrected in zip(self.model.requests[::2], self.model.requests[1::2]):
            self.assertEqual(corrected['messages'][0], original['messages'][0])
            self.assertEqual(len(corrected['messages']), 3)
            assistant, feedback = corrected['messages'][1:]
            self.assertEqual(feedback['role'], 'tool')
            self.assertEqual(feedback['tool_call_id'], assistant['tool_calls'][0]['id'])
            self.assertIn('300', feedback['content'])
            self.assertIn('280', feedback['content'])
        self.assertEqual(self.count_events('conversation_started'), 8)
        self.assertEqual(self.count_events('conversation_ended'), 8)
        self.assertEqual(self.count_events('tool_execution_failed'), 8)
        self.assertEqual(self.count_events('tool_execution_completed'), 8)
        self.assertEqual(self.count_events('configuration_compared'), 4)
        self.assertEqual(self.count_events('simulation_submitted'), 5)
        data = ExperimentStatusDb(self.db).read()
        data['latest_config'] = data['state'].config
        self.assertEqual([section['status'] for section in experiment_sections(data)], ['Saved', 'Saved'])

    def test_socket_timeout_discards_corrections_and_restarts_each_view_conversation(self):
        stages = [(name, tool) for name in VIEWS for tool in ('submit_view', 'submit_observations')]
        gates = {stage: Event() for stage in stages}
        for gate in gates.values():
            self.addCleanup(gate.set)
        attempts = Counter()
        waiting = []
        def record_wait(seconds):
            state = ExperimentDb(self.db).load()
            waiting.append((state.view_name, state.phase))
            self.assertEqual(state.observations, {})
        respond = self.model.respond
        def stalled(request):
            stage = requested_view(request), request['tools'][0]['function']['name']
            attempts[stage] += 1
            response = respond(request)
            if attempts[stage] == 2:
                gates[stage].wait(5)
            elif attempts[stage] == 3:
                gates[stage].set()
            if attempts[stage] == 1:
                function = response['choices'][0]['message']['tool_calls'][0]['function']
                arguments = json.loads(function['arguments'])
                field = 'hypothesis' if stage[1] == 'submit_view' else 'observations'
                arguments[field] = 'x' * 300
                function['arguments'] = json.dumps(arguments)
            return response
        self.model.respond = stalled
        self.scores = iter((10, 11, 12, 13, 14))
        with patch.object(DAx3l, 'HTTP_TIMEOUT_SECONDS', .1), \
                patch('ax3l.app.experiment.ExperimentLoop.sleep', side_effect=record_wait) as delay, \
                patch('ax3l.app.experiment.ExperimentLoop.shuffle', side_effect=lambda names: names.reverse()), \
                self.assertLogs(level='WARNING'):
            self.assertEqual(self.service(cycles=4), 0)
        self.assertEqual(attempts, Counter({stage: 3 for stage in stages}))
        self.assertEqual(waiting, [(name, phase) for name in reversed(VIEWS)
                         for phase in ('choosing', 'evaluating')])
        self.assertEqual(delay.call_args_list, [call(DAx3l.LLM_TIMEOUT_RETRY_SECONDS)] * 8)
        self.assertEqual(self.request_steps(), [(name, tool) for name in reversed(VIEWS)
                         for tool in ('submit_view', 'submit_observations') for _ in range(3)])
        for original, correction, restarted in zip(self.model.requests[::3], self.model.requests[1::3],
                                                    self.model.requests[2::3]):
            self.assertEqual(len(correction['messages']), 3)
            self.assertEqual(correction['messages'][-1]['role'], 'tool')
            self.assertEqual(len(restarted['messages']), 1)
            self.assertEqual(restarted, original)
        prompts = self.db.query('''SELECT parent_event_id, process_id, parameter, source_name
            FROM events WHERE name='prompt_sent' AND event_id > %s ORDER BY event_id''', (self.start_event,))
        for original, correction, restarted in zip(prompts[::3], prompts[1::3], prompts[2::3]):
            self.assertEqual(original['parent_event_id'], correction['parent_event_id'])
            self.assertNotEqual(original['parent_event_id'], restarted['parent_event_id'])
            for field in ('process_id', 'parameter', 'source_name'):
                self.assertEqual(original[field], restarted[field])
        self.assertEqual(self.count_events('llm_request_failed'), 8)
        self.assertEqual(self.count_events('tool_execution_failed'), 8)
        self.assertEqual(self.count_events('conversation_started'), 16)
        self.assertEqual(self.count_events('conversation_ended'), 16)
        self.assertEqual(self.count_events('simulation_submitted'), 5)
        self.assertEqual(self.count_events('configuration_compared'), 4)
        self.assertEqual(self.count_events('golden_config_created'), 5)
        self.assertEqual(ExperimentDb(self.db).load().phase, 'completed')

    def test_http_request_and_gateway_timeouts_recover_without_restarting(self):
        attempts = Counter()
        respond = self.model.respond
        def timeout_status(request):
            tool = request['tools'][0]['function']['name']
            stage = requested_view(request), tool
            attempts[stage] += 1
            self.model.status = 200
            if attempts[stage] == 1:
                self.model.status = 408 if tool == 'submit_view' else 504
            return respond(request)
        self.model.respond = timeout_status
        self.scores = iter((10, 11, 12, 13, 14))
        with patch('ax3l.app.experiment.ExperimentLoop.sleep') as delay, self.assertLogs(level='WARNING'):
            self.assertEqual(self.service(cycles=4), 0)
        self.assertEqual(len(attempts), 8)
        self.assertTrue(all(count == 2 for count in attempts.values()))
        self.assertEqual(delay.call_args_list, [call(DAx3l.LLM_TIMEOUT_RETRY_SECONDS)] * 8)
        self.assertEqual(self.count_events('llm_request_failed'), 8)
        self.assertEqual(self.count_events('tool_execution_completed'), 8)
        self.assertEqual(self.count_events('simulation_submitted'), 5)
        self.assertEqual(self.count_events('configuration_compared'), 4)

    def test_timeout_during_length_correction_can_stop_and_resume_without_repeating_the_run(self):
        respond = self.model.respond
        attempts = Counter()
        def timeout_correction(request):
            tool = request['tools'][0]['function']['name']
            attempts[tool] += 1
            response = respond(request)
            if tool == 'submit_observations':
                if attempts[tool] == 1:
                    function = response['choices'][0]['message']['tool_calls'][0]['function']
                    function['arguments'] = json.dumps(dict(observations='x' * 300))
                else:
                    self.model.status = 504
            return response
        self.model.respond = timeout_correction
        self.scores = iter((10, 11, 12, 13, 14))
        with patch('ax3l.app.experiment.ExperimentLoop.sleep', side_effect=KeyboardInterrupt()), \
                self.assertLogs(level='WARNING'):
            self.assertEqual(self.service(), 130)
        pending = ExperimentDb(self.db).load()
        self.assertEqual(pending.phase, 'evaluating')
        self.assertEqual(pending.observations, {})
        self.assertEqual(len(self.model.requests[-1]['messages']), 3)
        self.assertEqual(self.count_events('tool_execution_failed'), 1)
        self.assertEqual(self.count_events('llm_request_failed'), 1)
        self.model.respond, self.model.status = respond, 200
        self.assertEqual(self.service(cycles=4), 0)
        self.assertEqual(len(self.model.requests[3]['messages']), 1)
        self.assertEqual(self.request_steps()[:4], [(pending.view_name, tool) for tool in
                         ('submit_view', 'submit_observations', 'submit_observations', 'submit_observations')])
        self.assertEqual(self.count_events('proposal_accepted'), 4)
        self.assertEqual(self.count_events('simulation_submitted'), 5)
        self.assertEqual(self.count_events('configuration_compared'), 4)
        self.assertEqual(ExperimentDb(self.db).load().view_index, 3)

    def test_sixteen_losses_rotate_seed_and_keep_the_next_view(self):
        self.scores = iter((10,) + (9,) * 16 + (4, 5))
        with patch('ax3l.app.experiment.ExperimentLoop.shuffle',
                   side_effect=lambda names: names.reverse()) as shuffle:
            self.assertEqual(self.service(cycles=16), 0)
            before = ExperimentDb(self.db).load()
            self.assertEqual(before.failures, 16)
            self.assertEqual(before.view_index, 3)
            self.assertEqual(self.count_events('simulation_submitted'), 17)
            self.assertEqual(self.service(), 0)
        state = ExperimentDb(self.db).load()
        self.assertEqual(state.view_name, list(reversed(VIEWS))[0])
        self.assertEqual(state.view_index, 0)
        self.assertEqual(shuffle.call_count, 5)
        self.assertEqual(state.config['seed'], before.config['seed'] + 1)
        self.assertEqual(state.failures, 0)
        self.assertEqual(state.golden_history.view, state.view_name)
        rows = self.db.query('SELECT seed FROM configurations JOIN simulation_runs USING (run_id) ORDER BY id')
        self.assertEqual([row['seed'] for row in rows], [before.config['seed']] * 17 + [state.config['seed']] * 2)
        self.assertEqual(self.count_events('configuration_compared'), 17)
        self.assertEqual(self.count_events('golden_config_created'), 3)
        evaluations = [name for name, tool in self.request_steps() if tool == 'submit_observations']
        self.assertEqual(evaluations, list(reversed(VIEWS)) * 4 + [state.view_name])

    def test_service_runs_four_separate_views_and_persists_golden_evidence(self):
        self.scores = iter((10, 11, 9, 11, 8))
        self.assertEqual(self.service(cycles=4), 0)
        rows = self.db.query('SELECT run_id, high_score FROM simulation_runs ORDER BY id')
        self.assertEqual(len(rows), 5)
        self.assertEqual(len(self.model.requests), 8)
        state = ExperimentDb(self.db).load()
        self.assertEqual(state.phase, 'completed')
        self.assertEqual(state.view_index, 3)
        self.assertEqual(state.golden_run_id, rows[3]['run_id'])
        self.assertEqual(state.latest_run_id, rows[4]['run_id'])
        self.assertEqual(state.golden_history.latest_run_id, rows[3]['run_id'])
        self.assertEqual(state.golden_history.reference_run_id, rows[1]['run_id'])
        self.assertEqual(state.failures, 1)
        for name, expected in (('conversation_started', 8), ('conversation_ended', 8),
                               ('configuration_compared', 4), ('proposal_accepted', 4),
                               ('simulation_submitted', 5), ('simulation_completed', 5),
                               ('golden_config_created', 3)):
            self.assertEqual(self.count_events(name), expected)

    def test_restart_keeps_order_and_skips_accepted_proposal(self):
        save = ExperimentDb.save
        def stop(store, state):
            save(store, state)
            if state.phase == 'ready' and state.proposals:
                raise KeyboardInterrupt()
        with patch.object(ExperimentDb, 'save', stop), \
                patch('ax3l.app.experiment.ExperimentLoop.shuffle', side_effect=lambda names: names.reverse()):
            self.assertEqual(self.service(), 130)
        order = ExperimentDb(self.db).load().order
        self.assertEqual(len(self.model.requests), 1)
        self.assertEqual(self.service(), 0)
        self.assertEqual(len(self.model.requests), 2)
        self.assertEqual(self.count_events('simulation_submitted'), 2)
        self.assertEqual(self.service(), 0)
        self.assertEqual(ExperimentDb(self.db).load().order, order)
        self.assertEqual(ExperimentDb(self.db).load().view_index, 1)

    def test_submission_with_lost_acknowledgement_is_not_repeated(self):
        submit = SnakeLab.submit_simulation
        def lost_reply(snake, config):
            submit(snake, config)
            raise TimeoutError('Lost acknowledgement')
        with patch.object(SnakeLab, 'submit_simulation', lost_reply):
            with self.assertRaises(TimeoutError):
                self.service()
        self.assertEqual(ExperimentDb(self.db).load().phase, 'submitting')
        self.assertEqual(self.service(), 0)
        self.assertEqual(self.db.query('SELECT COUNT(*) AS n FROM simulation_runs')[0]['n'], 2)
        self.assertEqual(len(self.model.requests), 2)

    def test_restart_after_comparison_preserves_counter_and_single_promotion(self):
        save = ExperimentDb.save
        def stop(store, state):
            if state.phase == 'evaluating':
                raise KeyboardInterrupt()
            save(store, state)
        with patch.object(ExperimentDb, 'save', stop):
            self.assertEqual(self.service(), 130)
        self.assertEqual(ExperimentDb(self.db).load().phase, 'comparing')
        self.assertEqual(self.service(), 0)
        self.assertEqual(len(self.model.requests), 2)
        self.assertEqual(ExperimentDb(self.db).load().failures, 1)
        self.assertEqual(self.count_events('configuration_compared'), 1)
        self.assertEqual(self.count_events('golden_config_created'), 1)

    def test_checkpoint_write_rolls_back_envelope_and_preserves_previous_snapshot(self):
        store = ExperimentDb(self.db)
        state = ExperimentState(str(uuid4()), 'ready', SimulationConfiguration.defaults(), baseline=True)
        store.save(state)
        previous = deepcopy(state)
        execute = self.db.execute
        def fail_message(sql, params=None):
            if 'INSERT INTO event_messages' in sql:
                raise RuntimeError('Checkpoint message failed')
            return execute(sql, params)
        state.phase = 'submitting'
        with patch.object(self.db, 'execute', side_effect=fail_message):
            with self.assertRaisesRegex(RuntimeError, 'Checkpoint message failed'):
                store.save(state)
        self.assertEqual(store.load(), previous)
        self.assertEqual(self.count_events('view_experiment_state_saved'), 1)

    def test_seed_baseline_restart_keeps_pending_view_and_clears_history(self):
        self.scores = iter((10, 11, 4, 3))
        self.assertEqual(self.service(), 0)
        store = ExperimentDb(self.db)
        state = store.load()
        state.failures = 16
        store.save(state)
        save = ExperimentDb.save
        def stop(store, state):
            if state.seed_baseline and state.phase == 'completed':
                raise KeyboardInterrupt()
            save(store, state)
        with patch.object(ExperimentDb, 'save', stop):
            self.assertEqual(self.service(), 130)
        self.assertTrue(store.load().seed_baseline)
        self.assertEqual(self.service(), 0)
        rows = self.db.query('SELECT seed FROM configurations ORDER BY seed')
        self.assertEqual([row['seed'] for row in rows], [1970, 1970, 1971, 1971])
        self.assertEqual(store.load().view_index, 1)
        self.assertEqual(store.load().failures, 1)
        self.assertIsNone(store.load().golden_history)
        self.assertEqual(self.count_events('golden_config_created'), 3)
        self.assertEqual(self.count_events('configuration_compared'), 2)
