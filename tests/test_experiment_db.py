"""Draft recovery and analysis queries against disposable MariaDB fixtures."""

from copy import deepcopy
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from ax3l.app.DbMgr import DbMgr
from ax3l.app.snakelab.ExperimentDb import ExperimentDb
from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb
from ax3l.app.snakelab.SubmitSimulationSummaryHandler import SubmitSimulationSummaryHandler
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


@unittest.skipUnless(os.environ.get('AX3L_TEST_DB') == '1', 'requires disposable MariaDB test database')
class ExperimentDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ['DB_NAME'], 'ax3l_test')
        self.db = DbMgr()
        self.addCleanup(self.db.close)
        self.process_ids = [str(uuid4()), str(uuid4())]
        self.addCleanup(self.cleanup_events)

    def cleanup_events(self):
        for process_id in self.process_ids:
            self.db.execute('DELETE FROM events WHERE process_id = %s ORDER BY event_id DESC', (process_id,))

    def test_draft_snapshot_survives_a_new_connection_and_keeps_the_next_choice(self):
        draft_id, golden_id = self.process_ids
        draft = ConfigurationDraft(draft_id, golden_id, {'golden': golden_id}, SimulationConfiguration.defaults())
        experiments = ExperimentDb(self.db)
        experiments.save_draft(draft)
        draft.selections = ['hidden_size']
        draft.config['model']['hidden_size'] = 240
        experiments.save_draft(draft)
        other = DbMgr(initialize_event_tables=False)
        try:
            restored = ExperimentDb(other).draft(draft_id)
        finally:
            other.close()
        self.assertEqual(restored, draft)
        self.assertEqual(restored.next_parameter, 'sequence_length')
        restored.config['model']['hidden_size'] = 272
        self.assertEqual(experiments.draft(draft_id).config['model']['hidden_size'], 240)

    def test_summary_persists_computed_facts_once_and_reuses_the_original(self):
        run_id = self.process_ids[1]
        config = SimulationConfiguration.defaults()
        with patch('ax3l.app.snakelab.SubmitSimulationSummaryHandler.SnakeLab') as snake:
            snake.return_value.get_run_result.return_value = dict(status='completed', high_score=9, config=config)
            snake.return_value.get_analysis_episodes.return_value = [dict(
                episode=1, score=9, steps=10, outcome='wall', loss=None, epsilon=.9,
                epsilon_injections=2, epsilon_nice_injections=0)]
            handler = SubmitSimulationSummaryHandler(self.db)
            text = 'One episode reached nine points. It ended at a wall with no recorded loss.'
            self.assertEqual(handler.submit({'run_id': run_id, 'summary': text})['status'], 'ok')
            self.assertEqual(handler.submit({'run_id': run_id, 'summary': 'Different words. Another sentence.'})['status'], 'ok')
        saved = ExperimentDb(self.db).analysis(run_id)
        self.assertEqual(saved.summary, text)
        self.assertEqual(saved.metrics['termination_reasons']['wall'], {'count': 1, 'percent': 100})
        self.assertEqual(saved.metrics['episodes_with_loss'], 0)
        self.assertEqual(saved.config, config)
        count = self.db.query("SELECT COUNT(*) AS n FROM events WHERE process_id=%s AND name='simulation_analyzed'", (run_id,))[0]['n']
        self.assertEqual(count, 1)
        self.db.execute('DELETE FROM events WHERE process_id = %s', (run_id,))
        self.assertIsNone(ExperimentDb(self.db).analysis(run_id))

    def test_reference_selection_uses_completed_runs_and_stable_ties(self):
        self.db.execute('''CREATE TEMPORARY TABLE simulation_runs (
            id INTEGER PRIMARY KEY, run_id VARCHAR(36), status VARCHAR(16), high_score INTEGER,
            completed_at DATETIME(6))''')
        for row in ((1, 'early-best', 'completed', 30, '2026-11-15 10:00:00'),
                    (2, 'tied-best', 'completed', 30, '2026-11-15 11:00:00'),
                    (3, 'running', 'running', 100, None),
                    (4, 'latest', 'completed', 10, '2026-11-15 12:00:00'),
                    (5, 'failed', 'failed', 100, '2026-11-15 13:00:00'),
                    (6, 'unscored', 'completed', None, '2026-11-15 14:00:00')):
            self.db.execute('INSERT INTO simulation_runs VALUES (%s,%s,%s,%s,%s)', row)
        source = SnakeLabDb(self.db)
        self.assertEqual(source.get_latest_completed_run_id(), 'latest')
        self.assertEqual(source.get_all_time_best_run_id(), 'early-best')
        self.db.execute("UPDATE simulation_runs SET completed_at='2026-11-15 15:00:00' WHERE id=1")
        self.assertEqual(source.get_latest_completed_run_id(), 'early-best')
        self.db.execute('DELETE FROM simulation_runs')
        self.assertIsNone(source.get_latest_completed_run_id())
        self.assertIsNone(source.get_all_time_best_run_id())

    def test_episode_analysis_read_preserves_missing_observations_and_order(self):
        self.db.execute('''CREATE TEMPORARY TABLE simulation_episodes (
            run_id VARCHAR(36), episode INTEGER, score INTEGER, steps INTEGER,
            epsilon DOUBLE, loss DOUBLE, outcome VARCHAR(16),
            epsilon_injections INTEGER, epsilon_nice_injections INTEGER)''')
        self.db.execute("INSERT INTO simulation_episodes VALUES ('run',2,4,20,0,.2,'snake',0,2), ('run',1,0,5,.9,NULL,NULL,3,0)")
        episodes = SnakeLabDb(self.db).get_analysis_episodes('run')
        self.assertEqual([row['episode'] for row in episodes], [1, 2])
        self.assertIsNone(episodes[0]['loss'])
        self.assertIsNone(episodes[0]['outcome'])
        self.assertEqual(episodes[1]['epsilon_nice_injections'], 2)
