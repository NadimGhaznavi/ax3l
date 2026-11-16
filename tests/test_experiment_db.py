"""Draft recovery and analysis queries against disposable MariaDB fixtures."""

from copy import deepcopy
from dataclasses import asdict
from datetime import timedelta
import json
import os
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from ax3l.app.DbMgr import DbMgr
from ax3l.activity.ExperimentActivity import item_activity
from ax3l.app.snakelab.ExperimentDb import ExperimentDb
from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb
from ax3l.app.snakelab.SubmitSimulationSummaryHandler import SubmitSimulationSummaryHandler
from ax3l.constants.DSimulationAnalysis import DSimulationAnalysis
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
from ax3l.entities.AnalysisTask import AnalysisTask
from ax3l.entities.SimulationAnalysis import SimulationAnalysis
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


class DraftRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.db = Mock()
        self.store = ExperimentDb(self.db)
        self.draft = ConfigurationDraft('draft', 'gold', {}, SimulationConfiguration.defaults())

    def restore(self, data):
        self.db.query.return_value = [dict(content=json.dumps(data))]
        return self.store.draft()

    def test_current_snapshots_preserve_parameter_selection_and_run_decisions(self):
        for phase, parameter in (('selecting_parameter', None), ('choosing', 'gamma'),
                                 ('reviewing', None), ('ready', None)):
            self.draft.phase, self.draft.parameter = phase, parameter
            self.assertEqual(self.restore(asdict(self.draft)), self.draft)

    def test_legacy_drafts_keep_the_in_progress_choice_then_use_qwens_next_decision(self):
        data = asdict(self.draft)
        del data['parameter']
        data.update(phase='choosing', selections=['hidden_size', 'layers', 'dropout'])
        self.assertEqual(self.restore(data).next_parameter, 'sequence_length')
        data['phase'] = 'preparing'
        restored = self.restore(data)
        self.assertEqual(restored.phase, 'choosing')
        self.assertEqual(restored.next_parameter, 'sequence_length')
        data['phase'] = 'ready'
        self.assertEqual(self.restore(data).phase, 'reviewing')
        for phase in ('submitting', 'submitted', 'completed'):
            data['phase'] = phase
            self.assertEqual(self.restore(data).phase, phase)


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
        draft.phase, draft.parameter = 'choosing', 'sequence_length'
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

    def test_report_states_use_latest_tasks_per_run_and_survive_new_connections(self):
        first, second = self.process_ids
        experiments = ExperimentDb(self.db)
        self.assertEqual(experiments.analysis_states([]), {})
        self.assertEqual(experiments.analysis_states([first])[first], dict(analysis=None, sections={}, task=None))
        experiments.save_analysis_task(AnalysisTask(first, 'scores', 'preparing'))
        experiments.save_analysis_task(AnalysisTask(first, 'scores', 'analyzing'))
        experiments.save_analysis_sections(first, {'scores': 'Saved.'})
        experiments.save_analysis_task(AnalysisTask(first, 'distribution', 'failed'))
        saved = SimulationAnalysis(second, SimulationConfiguration.defaults(), {}, 'Saved all images.')
        experiments.save_analysis(saved)
        self.db.log('simulation_analysis_task', 'Other', 'INFO', 'unrelated', process_id=first)
        other = DbMgr(initialize_event_tables=False)
        try:
            states = ExperimentDb(other).analysis_states([first, second])
        finally:
            other.close()
        self.assertEqual(states[first]['task'], AnalysisTask(first, 'distribution', 'failed'))
        self.assertEqual(states[first]['sections'], {'scores': 'Saved.'})
        self.assertIsNone(states[first]['analysis'])
        self.assertEqual(states[second]['analysis'], saved)
        self.assertIsNone(states[second]['task'])

    def test_sections_survive_restart_and_combine_once_with_computed_facts(self):
        run_id = self.process_ids[1]
        config = SimulationConfiguration.defaults()
        with patch('ax3l.app.snakelab.SubmitSimulationSummaryHandler.SnakeLab') as snake:
            snake.return_value.get_run_result.return_value = dict(status='completed', high_score=9, config=config)
            snake.return_value.get_analysis_episodes.return_value = [dict(
                episode=1, score=9, steps=10, outcome='wall', loss=None, epsilon=.9,
                epsilon_injections=2, epsilon_nice_injections=0)]
            handler = SubmitSimulationSummaryHandler(self.db)
            summaries = {'scores': 'One episode reached nine points.',
                         'distribution': 'The only episode scored nine.', 'loss': 'No loss was recorded.'}
            self.assertEqual(handler.submit({'run_id': run_id, 'section': 'scores',
                                             'summary': summaries['scores']})['status'], 'ok')
            self.assertIsNone(ExperimentDb(self.db).analysis(run_id))
            other = DbMgr(initialize_event_tables=False)
            try:
                self.assertEqual(ExperimentDb(other).analysis_sections(run_id), {'scores': summaries['scores']})
                restarted = SubmitSimulationSummaryHandler(other)
                self.assertEqual(restarted.submit({'run_id': run_id, 'section': 'scores',
                                                   'summary': 'Replacement.'})['status'], 'ok')
                for section in ('distribution', 'loss'):
                    self.assertEqual(restarted.submit({'run_id': run_id, 'section': section,
                                                       'summary': summaries[section]})['status'], 'ok')
            finally:
                other.close()
            self.assertEqual(handler.submit({'run_id': run_id, 'section': 'loss',
                                             'summary': 'Different words.'})['status'], 'ok')
        saved = ExperimentDb(self.db).analysis(run_id)
        self.assertEqual(saved.summary, '\n'.join(f'{label}: {summaries[section]}'
                         for section, label in DSimulationAnalysis.SECTIONS.items()))
        self.assertEqual(saved.metrics['termination_reasons']['wall'], {'count': 1, 'percent': 100})
        self.assertEqual(saved.metrics['episodes_with_loss'], 0)
        self.assertEqual(saved.config, config)
        count = self.db.query("SELECT COUNT(*) AS n FROM events WHERE process_id=%s AND name='simulation_analyzed'", (run_id,))[0]['n']
        self.assertEqual(count, 1)
        self.db.execute('DELETE FROM events WHERE process_id = %s', (run_id,))
        self.assertIsNone(ExperimentDb(self.db).analysis(run_id))
        self.assertEqual(ExperimentDb(self.db).analysis_sections(run_id), {})

    def test_checklist_activity_uses_database_time_and_omits_image_payloads(self):
        run_id, draft_id = self.process_ids
        started = self.db.query('SELECT CURRENT_TIMESTAMP(6) AS stamp')[0]['stamp'] - timedelta(minutes=5)

        def event(name, content, seconds, *, process=run_id, parent=None, parameter=None, source=None):
            category = 'SnakeLab' if name == 'simulation_analysis_task' else 'Conversation'
            event_id = self.db.log(name, category, 'INFO', content, process_id=process,
                                   parent_event_id=parent, parameter=parameter, source_name=source)
            self.db.execute('UPDATE events SET occurred_at=%s WHERE event_id=%s',
                            (started + timedelta(seconds=seconds), event_id))
            return event_id

        event('simulation_analysis_task', json.dumps(dict(section='scores', phase='preparing')), 0)
        conversation = event('conversation_started', 'Started', 5)
        image = event('prompt_sent', json.dumps(dict(content=[
            dict(type='text', text='Scores'),
            dict(type='image_url', image_url=dict(url='data:image/png;base64,cG5n'))])), 6,
            parent=conversation, parameter='simulation_summary', source='AnalyzeSimulation')
        event('reply_received', json.dumps(dict(usage=dict(total_tokens=100))), 10, parent=conversation)
        event('reply_received', json.dumps(dict(usage=dict(total_tokens=150))), 20, parent=conversation)
        event('conversation_ended', 'Done', 22, parent=conversation)
        event('simulation_analysis_task', json.dumps(dict(section='scores', phase='saved')), 25)
        event('simulation_analysis_task', json.dumps(dict(section='loss', phase='preparing')), 30)
        conversation = event('conversation_started', 'Started', 35, process=draft_id)
        event('prompt_sent', json.dumps(dict(content='Choose')), 36, process=draft_id,
              parent=conversation, parameter='epsilon_pair', source='ConfigurationChoice')
        event('reply_received', json.dumps(dict(usage=dict(total_tokens=300))), 40,
              process=draft_id, parent=conversation)
        event('conversation_ended', 'Done', 45, process=draft_id, parent=conversation)
        self.db.log('reply_received', 'Other', 'INFO', 'Not JSON', process_id=run_id)
        other = DbMgr(initialize_event_tables=False)
        try:
            events = ExperimentDb(other).activity_events([run_id, draft_id])
        finally:
            other.close()
        self.assertEqual(ExperimentDb(self.db).activity_events([]), [])
        self.assertNotIn('cG5n', json.dumps(events, default=str))
        work = item_activity(events)
        self.assertEqual(work[run_id, 'scores'], dict(seconds=25, tokens=250, image_event_id=image))
        self.assertEqual(work[draft_id, 'epsilon_pair'], dict(seconds=10, tokens=300, image_event_id=None))
        self.assertGreaterEqual(work[run_id, 'loss']['seconds'], 270)
        self.assertLess(work[run_id, 'loss']['seconds'], 280)

    def test_checklist_activity_preserves_unreported_tokens(self):
        run_id = self.process_ids[0]
        conversation = self.db.log('conversation_started', 'Conversation', 'INFO', 'Started', process_id=run_id)
        self.db.log('prompt_sent', 'Conversation', 'INFO', '{"content":"Choose"}',
                    process_id=run_id, parent_event_id=conversation, parameter='hidden_size')
        self.db.log('reply_received', 'Conversation', 'INFO', '{"choices":[]}',
                    process_id=run_id, parent_event_id=conversation)
        work = item_activity(ExperimentDb(self.db).activity_events([run_id]))
        self.assertIsNone(work[run_id, 'hidden_size']['tokens'])

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
