"""Run the service against disposable MariaDB and local HTTP/ZeroMQ fixtures.

Requires AX3L_TEST_DB=1 and DB_NAME=ax3l_test. The database must have no
simulation source tables; this fixture creates and removes its own tables.
"""

from copy import deepcopy
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from ax3l.interface.database.DbMgr import DbMgr
from ax3l.interface.database.ExperimentDb import ExperimentDb
from ax3l.interface.database.SnakeLabDb import CONFIGURATION_FIELDS, CONFIGURATION_COLUMNS, _config_values
from ax3l.constants.DSnakeLab import DSnakeLab
from ax3l.entities.ExperimentState import ExperimentState
from ax3l.interface.SimulationConfiguration import SimulationConfiguration
from ax3l.interface.SnakeLab import SnakeLab
from ax3l.server.Ax3lServer import main
from view_cycle_fixtures import LocalLLM, LocalSnakeControl, episodes, new_seed_proposal


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
        self.scores = iter((10, 12, 7))
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

    def test_service_completes_two_cycles_with_native_tools_and_real_database(self):
        self.assertEqual(self.service(cycles=2), 0)
        self.assertEqual(self.db.query('SELECT COUNT(*) AS n FROM simulation_runs')[0]['n'], 3)
        self.assertEqual(len(self.model.requests), 20)
        state = ExperimentDb(self.db).load()
        self.assertEqual(state.phase, 'completed')
        self.assertEqual(set(state.order), {'architecture', 'training', 'exploration', 'reward-signals'})
        self.assertEqual(len(state.proposals), 4)
        self.assertEqual(len(state.observations), 4)
        self.assertEqual(state.config['training']['sequence_length'], 8)
        self.assertEqual(state.config['training']['gamma'], .95)
        for path in ('training.sequence_length', 'training.gamma'):
            self.assertEqual(sum(path in proposal.values for proposal in state.proposals.values()), 1)
        rows = self.db.query('SELECT run_id, high_score FROM simulation_runs ORDER BY id')
        self.assertEqual(state.golden_run_id, rows[1]['run_id'])
        self.assertEqual(state.latest_run_id, rows[2]['run_id'])
        for name, expected in (('view_experiment_state_saved', None), ('conversation_started', 20),
                               ('conversation_ended', 20), ('configuration_compared', 2),
                               ('proposal_accepted', 2), ('simulation_submitted', 3),
                               ('simulation_completed', 3), ('golden_config_created', 2)):
            count = self.count_events(name)
            self.assertGreater(count, 0) if expected is None else self.assertEqual(count, expected)

    def test_restart_uses_saved_order_and_skips_accepted_views(self):
        save = ExperimentDb.save
        def stop(store, state):
            save(store, state)
            if state.phase == 'choosing' and len(state.proposals) == 2:
                raise KeyboardInterrupt()
        with patch.object(ExperimentDb, 'save', stop), \
                patch('ax3l.app.experiment.ExperimentLoop.shuffle', side_effect=lambda names: names.reverse()):
            self.assertEqual(self.service(), 130)
        order = ExperimentDb(self.db).load().order
        self.assertEqual(len(self.model.requests), 6)
        self.assertEqual(self.service(), 0)
        self.assertEqual(len(self.model.requests), 12)
        self.assertEqual(ExperimentDb(self.db).load().order, order)
        self.assertEqual(self.count_events('simulation_submitted'), 2)
        for index, path in ((6, 'training.sequence_length'), (7, 'training.gamma')):
            properties = self.model.requests[index]['tools'][0]['function']['parameters']['properties']
            self.assertNotIn(path, properties['values']['properties'])

    def test_restart_skips_saved_observations(self):
        save = ExperimentDb.save
        def stop(store, state):
            save(store, state)
            if state.phase == 'evaluating' and len(state.observations) == 2:
                raise KeyboardInterrupt()
        with patch.object(ExperimentDb, 'save', stop):
            self.assertEqual(self.service(), 130)
        self.assertEqual(len(ExperimentDb(self.db).load().observations), 2)
        self.assertEqual(len(self.model.requests), 2)
        self.assertEqual(self.service(), 0)
        self.assertEqual(len(self.model.requests), 12)
        self.assertEqual(len(ExperimentDb(self.db).load().observations), 4)

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
        self.assertEqual(len(self.model.requests), 12)

    def test_restart_after_promotion_does_not_repeat_comparison_or_promotion(self):
        save = ExperimentDb.save
        def stop(store, state):
            if state.phase == 'evaluating' and not state.baseline and state.proposals:
                raise KeyboardInterrupt()
            save(store, state)
        with patch.object(ExperimentDb, 'save', stop):
            self.assertEqual(self.service(), 130)
        self.assertEqual(ExperimentDb(self.db).load().phase, 'comparing')
        self.assertEqual(self.service(), 0)
        self.assertEqual(len(self.model.requests), 12)
        self.assertEqual(self.count_events('configuration_compared'), 1)
        self.assertEqual(self.count_events('golden_config_created'), 2)
        self.assertEqual(self.count_events('simulation_completed'), 2)

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

    def test_seed_request_runs_golden_then_candidate_on_the_incremented_seed(self):
        self.model.respond = new_seed_proposal
        self.scores = iter((10, 4, 8))
        self.assertEqual(self.service(), 0)
        rows = self.db.query('''SELECT r.run_id, r.high_score, c.seed, c.training_learning_rate
            FROM simulation_runs r JOIN configurations c USING (run_id) ORDER BY r.id''')
        self.assertEqual([row['seed'] for row in rows], [1970, 1971, 1971])
        self.assertEqual([row['training_learning_rate'] for row in rows], [.001, .001, .002])
        state = ExperimentDb(self.db).load()
        self.assertTrue(state.new_seed)
        self.assertFalse(state.seed_baseline)
        self.assertEqual(state.reference_run_id, rows[1]['run_id'])
        self.assertEqual(state.golden_run_id, rows[2]['run_id'])
        comparison = ExperimentDb(self.db).comparison(rows[2]['run_id'])
        self.assertEqual(comparison['golden_run_id'], rows[1]['run_id'])
        self.assertEqual(self.count_events('golden_config_created'), 3)
        self.assertEqual(self.count_events('configuration_compared'), 1)
        self.assertEqual(len(self.model.requests), 12)

    def test_seed_request_stays_read_only_after_restart_during_view_selection(self):
        self.model.respond = new_seed_proposal
        save = ExperimentDb.save
        def stop(store, state):
            save(store, state)
            if state.phase == 'choosing' and len(state.proposals) == 1:
                raise KeyboardInterrupt()
        with patch.object(ExperimentDb, 'save', stop):
            self.assertEqual(self.service(), 130)
        self.assertTrue(ExperimentDb(self.db).load().new_seed)
        self.assertEqual(self.service(), 0)
        for request in self.model.requests[5:8]:
            properties = request['tools'][0]['function']['parameters']['properties']['values']['properties']
            self.assertNotIn('new seed', properties)
            self.assertIn('"new seed": true', request['messages'][0]['content'])
        self.assertEqual(self.count_events('simulation_submitted'), 3)

    def test_restart_after_seed_baseline_promotion_does_not_run_it_again(self):
        self.model.respond = new_seed_proposal
        self.scores = iter((10, 4, 8))
        save = ExperimentDb.save
        def stop(store, state):
            if state.new_seed and not state.seed_baseline and state.phase == 'ready':
                raise KeyboardInterrupt()
            save(store, state)
        with patch.object(ExperimentDb, 'save', stop):
            self.assertEqual(self.service(), 130)
        state = ExperimentDb(self.db).load()
        self.assertEqual(state.phase, 'comparing')
        self.assertTrue(state.seed_baseline)
        self.assertEqual(self.count_events('golden_config_created'), 2)
        self.assertEqual(self.service(), 0)
        self.assertEqual(self.count_events('golden_config_created'), 3)
        self.assertEqual(self.count_events('simulation_submitted'), 3)
        self.assertEqual(len(self.model.requests), 12)

    def check_lost_seed_run_reply(self, submission_number):
        self.model.respond = new_seed_proposal
        submit = SnakeLab.submit_simulation
        def lost_reply(snake, config):
            run_id = submit(snake, config)
            if self.db.query('SELECT COUNT(*) AS n FROM simulation_runs')[0]['n'] == submission_number:
                raise TimeoutError('Lost acknowledgement')
            return run_id
        with patch.object(SnakeLab, 'submit_simulation', lost_reply):
            with self.assertRaises(TimeoutError):
                self.service()
        state = ExperimentDb(self.db).load()
        self.assertEqual(state.phase, 'submitting')
        self.assertEqual(state.seed_baseline, submission_number == 2)
        self.assertEqual(self.service(), 0)
        self.assertEqual(self.db.query('SELECT COUNT(*) AS n FROM simulation_runs')[0]['n'], 3)
        self.assertEqual(self.count_events('simulation_submitted'), 3)
        self.assertEqual(len(self.model.requests), 12)

    def test_lost_seed_baseline_reply_is_reconciled_without_resubmission(self):
        self.check_lost_seed_run_reply(2)

    def test_lost_seed_candidate_reply_is_reconciled_without_resubmission(self):
        self.check_lost_seed_run_reply(3)
