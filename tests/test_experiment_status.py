"""Configuration checklist semantics, lifecycle states, and report navigation."""

from copy import deepcopy
import os
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen
from uuid import uuid4

from ax3l.activity.ExperimentStatus import experiment_status
from ax3l.app.DbMgr import DbMgr
from ax3l.app.snakelab.ExperimentDb import ExperimentDb
from ax3l.entities.ConfigurationDraft import ConfigurationDraft, PARAMETER_ORDER
from ax3l.entities.SimulationAnalysis import SimulationAnalysis
from ax3l.interface.SimulationConfiguration import SimulationConfiguration
from ax3l.server.ReportingServer import make_server


class ExperimentStatusTests(unittest.TestCase):
    def setUp(self):
        self.draft = ConfigurationDraft(str(uuid4()), str(uuid4()), {}, SimulationConfiguration.defaults())
        self.golden = dict(status='completed', high_score=20, config=deepcopy(self.draft.config))

    def report(self, **kwargs):
        return experiment_status(self.draft, golden=self.golden, **kwargs)

    def test_saved_unchanged_values_count_and_paired_rows_advance_together(self):
        self.assertEqual(self.report()['phase'], 'Choosing: Hidden Size')
        self.draft.selections = PARAMETER_ORDER[:5]
        report = self.report()
        self.assertEqual(report['choices_selected'], 5)
        self.assertEqual(report['choices_total'], 8)
        rows = report['rows']
        self.assertEqual(len(rows), 11)
        self.assertEqual([row['path'] for row in rows], [
            'model.hidden_size', 'training.sequence_length', 'training.batch_size',
            'training.learning_rate', 'training.gamma', 'epsilon.initial', 'epsilon.decay',
            'game.rewards.closer_to_food', 'game.rewards.further_from_food',
            'epsilon_nice.probability', 'epsilon_nice.steps'])
        self.assertTrue(all(row['selected'] for row in rows[:5]))
        self.assertTrue(all(not row['selected'] for row in rows[5:]))
        self.assertEqual([row['path'] for row in rows if row['current']], ['epsilon.initial', 'epsilon.decay'])
        self.assertEqual(rows[5]['value'], str(self.golden['config']['epsilon']['initial']))
        self.assertEqual(self.draft.config, self.golden['config'])
        self.draft.selections.append('epsilon_pair')
        report = self.report()
        self.assertTrue(all(row['selected'] for row in report['rows'][:7]))
        self.assertEqual([row['path'] for row in report['rows'] if row['current']],
                         ['game.rewards.closer_to_food', 'game.rewards.further_from_food'])

    def test_ready_submitting_and_simulation_states(self):
        self.draft.selections = PARAMETER_ORDER.copy()
        for phase, label in [('ready', 'Ready to submit'), ('submitting', 'Submission pending')]:
            self.draft.phase = phase
            report = self.report()
            self.assertEqual(report['phase'], label)
            self.assertFalse(any(row['current'] for row in report['rows']))
        self.assertIn('not retried automatically', report['detail'])
        self.draft.phase = 'submitted'
        self.draft.run_id = str(uuid4())
        self.assertEqual(self.report()['phase'], 'Simulation unavailable')
        for state in ('queued', 'running', 'paused', 'cancelling', 'cancelled', 'failed'):
            with self.subTest(state=state):
                report = self.report(run=dict(status=state, high_score=17))
                self.assertEqual(report['phase'], f'Simulation {state}')
                self.assertIsNone(report['high_score'])
                self.assertIsNone(report['difference'])
                self.assertEqual(report['analysis_status'], 'Pending')
                if state in ('cancelled', 'failed'):
                    self.assertEqual(report['outcome'], 'No completed result')

    def test_finished_run_is_distinct_from_comparison_and_analysis(self):
        self.draft.selections = PARAMETER_ORDER.copy()
        self.draft.phase = 'submitted'
        self.draft.run_id = str(uuid4())
        run = dict(status='completed', high_score=25)
        report = self.report(run=run)
        self.assertEqual(report['phase'], 'Comparing results')
        self.assertEqual(report['outcome'], 'Awaiting comparison')
        comparison = {'current_golden_run_id': self.draft.run_id}
        report = self.report(run=run, comparison=comparison, sections={'scores': 'Scores improved.'})
        self.assertEqual(report['phase'], 'Analyzing simulation')
        self.assertIn('Score distribution', report['detail'])
        self.assertEqual(report['analysis_status'], 'In progress (1/3)')
        self.assertEqual(report['outcome'], 'New golden')
        self.assertEqual(report['target_score'], 20)
        self.assertEqual(report['difference'], 5)
        self.draft.phase = 'completed'
        report = self.report(run=run, comparison=comparison,
                             analysis=SimulationAnalysis(self.draft.run_id, self.draft.config, {}, 'Saved.'))
        self.assertEqual(report['phase'], 'Complete')
        self.assertEqual(report['analysis_status'], 'Complete')

    def test_zero_ties_and_lower_scores_retain_golden(self):
        self.draft.selections = PARAMETER_ORDER.copy()
        self.draft.phase = 'submitted'
        self.draft.run_id = str(uuid4())
        for score, target in [(0, 0), (20, 20), (0, 20), (19, 20)]:
            with self.subTest(score=score, target=target):
                self.golden['high_score'] = target
                report = self.report(run=dict(status='completed', high_score=score),
                                     comparison={'current_golden_run_id': self.draft.golden_run_id})
                self.assertEqual(report['high_score'], score)
                self.assertEqual(report['difference'], score - target)
                self.assertEqual(report['outcome'], 'Golden retained')


class ExperimentStatusHttpTests(unittest.TestCase):
    def setUp(self):
        self.db = self.enterContext(patch('ax3l.server.ReportingServer.DbMgr')).return_value
        self.experiments = self.enterContext(patch('ax3l.server.ReportingServer.ExperimentDb')).return_value
        self.snake = self.enterContext(patch('ax3l.server.ReportingServer.SnakeLab')).return_value
        self.draft = ConfigurationDraft(str(uuid4()), str(uuid4()), {}, SimulationConfiguration.defaults())
        self.experiments.draft.return_value = self.draft
        self.experiments.last_completed_draft.return_value = None
        self.experiments.comparison.return_value = None
        self.experiments.analysis.return_value = None
        self.experiments.analysis_sections.return_value = {}
        self.snake.get_run_result.return_value = dict(status='completed', high_score=0)
        server = make_server('127.0.0.1', 0)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        self.base = f'http://127.0.0.1:{server.server_port}'

    def get(self, path='/experiment-status'):
        with urlopen(self.base + path) as response:
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            return response.read().decode()

    def test_live_checklist_refresh_and_preserved_completed_view(self):
        page = self.get()
        self.assertIn('Choosing: Hidden Size', page)
        self.assertIn('0 / 8 choices saved', page)
        self.assertEqual(page.count('type="checkbox" disabled'), 11)
        self.assertIn('pending · inherited', page)
        self.assertIn('window.setTimeout(refreshStatus, 5000)', page)
        self.assertIn('Showing the last successful report', page)
        self.assertIn('cache: \'no-store\'', page)
        self.assertIn('aria-current="page">Current</a>', page)
        self.assertIn('No completed experiments recorded yet.', self.get('/experiment-status?view=completed'))
        self.draft.selections = PARAMETER_ORDER.copy()
        self.draft.phase = 'completed'
        self.draft.run_id = str(uuid4())
        self.experiments.comparison.return_value = {'current_golden_run_id': self.draft.golden_run_id}
        self.experiments.analysis.return_value = SimulationAnalysis(self.draft.run_id, {}, {}, 'Saved.')
        completed = deepcopy(self.draft)
        self.experiments.last_completed_draft.return_value = completed
        self.experiments.draft.return_value = ConfigurationDraft(
            str(uuid4()), self.draft.golden_run_id, {}, SimulationConfiguration.defaults())
        self.assertIn('Choosing: Hidden Size', self.get())
        page = self.get('/experiment-status?view=completed')
        self.assertIn('aria-current="page">Last completed</a>', page)
        self.assertIn('id="experiment-phase" role="status">Complete</h2>', page)
        self.assertEqual(page.count('disabled checked'), 11)
        self.assertNotIn('pending · inherited', page)
        self.assertIn('<dt>High score</dt><dd>0</dd>', page)
        self.assertIn('<dt>Difference</dt><dd>+0</dd>', page)
        self.assertIn('Golden retained', page)
        self.assertIn(f'href="/simulations/{completed.run_id}"', page)
        self.snake.get_run_result.assert_any_call(completed.golden_run_id)

    def test_empty_invalid_view_and_database_failure_cleanup(self):
        self.experiments.draft.return_value = None
        self.assertIn('No configuration selections recorded yet.', self.get())
        self.snake.get_run_result.assert_not_called()
        for query in ('view=other', 'view=', 'view=current&view=completed'):
            with self.subTest(query=query), self.assertRaises(HTTPError) as error:
                self.get('/experiment-status?' + query)
            self.assertEqual(error.exception.code, 400)
        self.db.close.reset_mock()
        self.experiments.draft.side_effect = RuntimeError('database unavailable')
        with patch('ax3l.server.ReportingServer.traceback.print_exc'), self.assertRaises(HTTPError) as error:
            self.get()
        self.assertEqual(error.exception.code, 500)
        self.db.close.assert_called_once()


@unittest.skipUnless(os.environ.get('AX3L_TEST_DB') == '1', 'requires disposable MariaDB test database')
class CompletedDraftDatabaseTests(unittest.TestCase):
    def test_completed_snapshot_survives_new_active_and_failed_drafts(self):
        self.assertEqual(os.environ['DB_NAME'], 'ax3l_test')
        db = DbMgr()
        self.addCleanup(db.close)
        experiments = ExperimentDb(db)
        ids = [str(uuid4()) for _ in range(4)]
        for draft_id in ids:
            self.addCleanup(db.execute, 'DELETE FROM events WHERE process_id = %s', (draft_id,))
        older = ConfigurationDraft(ids[0], str(uuid4()), {}, SimulationConfiguration.defaults(),
                                   PARAMETER_ORDER.copy(), 'completed', str(uuid4()))
        experiments.save_draft(older)
        newer = deepcopy(older)
        newer.draft_id, newer.run_id = ids[1], str(uuid4())
        experiments.save_draft(newer)
        active = ConfigurationDraft(ids[2], newer.run_id, {}, SimulationConfiguration.defaults())
        experiments.save_draft(active)
        self.assertEqual(experiments.draft(), active)
        self.assertEqual(experiments.last_completed_draft(), newer)
        active.phase = 'failed'
        experiments.save_draft(active)
        # An unrelated message with the same JSON field is not an experiment.
        db.log('other_event', 'Configuration', 'INFO', '{"phase":"completed"}', process_id=ids[3])
        self.assertEqual(experiments.last_completed_draft(), newer)
