"""Configuration checklist semantics, lifecycle states, and report navigation."""

from copy import deepcopy
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen
from uuid import uuid4

from ax3l.activity.ExperimentStatus import _elapsed, experiment_status
from ax3l.constants.DChoice import REVISION_PARAMETER
from ax3l.constants.DAx3l import DAx3l
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
        return experiment_status(self.draft, golden=self.golden, decision_grace_seconds=300, **kwargs)

    def test_elapsed_uses_minutes_and_seconds_until_one_hour(self):
        for seconds, expected in [
            (None, '—'), (0, '00:00'), (0.05, '00:00'), (15, '00:15'),
            (59.999, '00:59'), (60, '01:00'), (70, '01:10'),
            (3599.999, '59:59'), (3600, '01:00:00'), (3661, '01:01:01'),
        ]:
            with self.subTest(seconds=seconds):
                self.assertEqual(_elapsed(seconds), expected)

    def test_countdown_follows_the_saved_deadline_across_decision_stages_and_grace(self):
        self.draft.decision_expires_at = 1000
        for phase in ('selecting_parameter', 'choosing', 'reviewing'):
            with self.subTest(phase=phase):
                self.draft.phase, self.draft.parameter = phase, 'gamma'
                for now, remaining in ((850.5, 149.5), (1030, -30), (1180, -180)):
                    with patch('ax3l.activity.ExperimentStatus.time', return_value=now):
                        self.assertEqual(self.report()['countdown'], dict(
                            remaining_seconds=remaining, grace_seconds=300, expiry_action='reset'))
        self.draft.selections = ['layers']
        for now, remaining in ((850, 150), (1030, -30), (1180, -180)):
            with self.subTest(now=now), patch('ax3l.activity.ExperimentStatus.time', return_value=now):
                self.assertEqual(self.report()['countdown'], dict(
                    remaining_seconds=remaining, grace_seconds=300, expiry_action='run'))

    def test_countdown_is_inactive_outside_decisions_or_without_a_saved_deadline(self):
        self.assertIsNone(self.report()['countdown'])
        self.draft.decision_expires_at = 1000
        for phase in ('preparing', 'ready', 'submitting', 'submitted', 'completed', 'failed'):
            with self.subTest(phase=phase):
                self.draft.phase = phase
                self.assertIsNone(self.report()['countdown'])

    def test_totals_sum_recorded_steps_and_count_paired_choices_once(self):
        self.assertEqual(self.report()['totals'], dict(
            elapsed='00:00', input_tokens=0, output_tokens=0, tokens=0))
        activity = {
            'hidden_size': dict(image_event_id=None, steps=[
                dict(seconds=0.6, input_tokens=0, output_tokens=0),
                dict(seconds=None, input_tokens=None, output_tokens=None),
            ]),
            'epsilon_pair': dict(image_event_id=None, steps=[
                dict(seconds=0.6, input_tokens=1234, output_tokens=321),
            ]),
            'reward_pair': dict(image_event_id=None, steps=[
                dict(seconds=3600, input_tokens=1350, output_tokens=50),
            ]),
        }
        report = self.report(activity=activity)
        self.assertEqual(report['totals'], dict(
            elapsed='01:00:01', input_tokens=2584, output_tokens=371, tokens=2955))
        rows = {row['path']: row for row in report['rows']}
        self.assertEqual(rows['epsilon.initial']['steps'], [])
        self.assertEqual(rows['epsilon.decay']['totals'], dict(
            elapsed='00:00', input_tokens=1234, output_tokens=321, tokens=1555))
        self.assertEqual(rows['game.rewards.further_from_food']['totals'], dict(
            elapsed='01:00:00', input_tokens=1350, output_tokens=50, tokens=1400))

    def test_food_reward_row_totals_sum_its_steps_and_skip_unrecorded_usage(self):
        activity = {'food': dict(image_event_id=None, steps=[
            dict(seconds=1, input_tokens=None, output_tokens=None),
            dict(seconds=None, input_tokens=None, output_tokens=None),
            dict(seconds=205, input_tokens=1803, output_tokens=1794),
            dict(seconds=0, input_tokens=None, output_tokens=None),
            dict(seconds=47, input_tokens=3735, output_tokens=439),
            dict(seconds=0, input_tokens=0, output_tokens=0),
        ])}
        report = self.report(activity=activity)
        food = next(row for row in report['rows'] if row['path'] == 'game.rewards.food')
        self.assertEqual(food['totals'], dict(
            elapsed='04:13', input_tokens=5538, output_tokens=2233, tokens=7771))
        self.assertEqual(report['totals'], food['totals'])

    def test_saved_values_and_current_pair_follow_qwens_explicit_selection(self):
        self.assertEqual(self.report()['phase'], 'Choosing a setting')
        self.draft.selections = ['hidden_size', 'layers', 'dropout', 'sequence_length',
                                 'batch_size', 'learning_rate', 'gamma']
        self.draft.phase, self.draft.parameter = 'choosing', 'epsilon_pair'
        report = self.report()
        self.assertEqual(report['choices_selected'], 7)
        self.assertEqual(report['choices_total'], 15)
        rows = report['rows']
        self.assertEqual(len(rows), 18)
        self.assertEqual([row['path'] for row in rows], [
            'game.rewards.food', 'game.rewards.wall', 'game.rewards.snake', 'game.rewards.empty',
            'model.hidden_size', 'model.layers', 'model.dropout', 'training.sequence_length', 'training.batch_size',
            'training.learning_rate', 'training.gamma', 'epsilon.initial', 'epsilon.decay',
            'game.rewards.closer_to_food', 'game.rewards.further_from_food',
            'epsilon_nice.probability', 'epsilon_nice.steps', 'seed'])
        self.assertEqual([row['path'] for row in rows if row['selected']], [
            'model.hidden_size', 'model.layers', 'model.dropout', 'training.sequence_length',
            'training.batch_size', 'training.learning_rate', 'training.gamma'])
        self.assertEqual([row['path'] for row in rows if row['current']], ['epsilon.initial', 'epsilon.decay'])
        self.assertEqual(next(row['value'] for row in rows if row['path'] == 'epsilon.initial'),
                         str(self.golden['config']['epsilon']['initial']))
        self.assertEqual(self.draft.config, self.golden['config'])
        self.draft.selections.append('epsilon_pair')
        self.draft.parameter = 'reward_pair'
        report = self.report()
        self.assertEqual(sum(row['selected'] for row in report['rows']), 9)
        self.assertEqual([row['path'] for row in report['rows'] if row['current']],
                         ['game.rewards.closer_to_food', 'game.rewards.further_from_food'])

    def test_seed_choice_has_its_own_pending_and_saved_checklist_row(self):
        self.draft.phase, self.draft.parameter = 'choosing', 'seed'
        seed = next(row for row in self.report()['rows'] if row['path'] == 'seed')
        self.assertTrue(seed['current'])
        self.assertFalse(seed['selected'])
        self.assertEqual(seed['label'], 'Random Seed')
        self.draft.config['seed'] += 1
        self.draft.selections = ['seed']
        self.draft.phase, self.draft.parameter = 'reviewing', None
        report = self.report()
        seed = next(row for row in report['rows'] if row['path'] == 'seed')
        self.assertTrue(seed['selected'])
        self.assertTrue(seed['changed'])
        self.assertEqual(seed['inherited_value'], '1970')
        self.assertEqual(seed['value'], '1971')
        self.assertEqual(report['choices_selected'], 1)

    def test_values_are_compared_with_the_starting_golden_configuration_per_field(self):
        self.golden['config']['model']['hidden_size'] = 96
        self.draft.config['model']['hidden_size'] = 96
        self.draft.config['model']['layers'] = 2
        self.draft.config['epsilon']['initial'] = 0.75
        self.draft.config['epsilon_nice']['steps'] = float(self.golden['config']['epsilon_nice']['steps'])
        self.draft.selections = PARAMETER_ORDER.copy()
        self.draft.phase = 'ready'
        inherited_config = deepcopy(self.golden['config'])
        rows = {row['path']: row for row in self.report()['rows']}
        self.assertEqual(rows['model.hidden_size']['inherited_value'], '96')
        self.assertEqual(rows['model.hidden_size']['value'], '96')
        self.assertFalse(rows['model.hidden_size']['changed'])
        self.assertEqual(rows['model.layers']['inherited_value'], '1')
        self.assertEqual(rows['model.layers']['value'], '2')
        self.assertEqual({name for name, row in rows.items() if row['changed']},
                         {'model.layers', 'epsilon.initial'})
        self.assertEqual(self.golden['config'], inherited_config)

    def test_ready_submitting_and_simulation_states(self):
        self.draft.selections = PARAMETER_ORDER.copy()
        for phase, label in [('ready', 'Ready to submit'), ('submitting', 'Submission pending')]:
            self.draft.phase = phase
            report = self.report()
            self.assertEqual(report['phase'], label)
            self.assertFalse(any(row['current'] for row in report['rows']))
        self.assertIn('confirm the simulation', report['detail'])
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

    def test_duplicate_selection_and_revised_branch_have_distinct_status_and_accounting(self):
        self.draft.selections = PARAMETER_ORDER.copy()
        self.draft.phase = 'selecting_parameter'
        work = {REVISION_PARAMETER: dict(image_event_id=None, steps=[
            dict(label='Qwen request', seconds=12, state='Complete', input_tokens=100, output_tokens=20),
        ])}
        report = self.report(activity=work)
        self.assertEqual(report['phase'], 'Choosing a setting to revise')
        self.assertEqual(report['choices_selected'], len(PARAMETER_ORDER))
        self.assertEqual([row['path'] for row in report['rows'] if row['current']], [REVISION_PARAMETER])
        self.assertIsNone(report['rows'][-1]['inherited_value'])
        self.assertFalse(report['rows'][-1]['changed'])
        self.assertEqual(report['totals'], dict(elapsed='00:12', input_tokens=100, output_tokens=20, tokens=120))
        self.assertEqual(report['rows'][-1]['totals'], report['totals'])
        self.draft.selections.remove('layers')
        self.draft.phase = 'choosing'
        self.draft.parameter = 'layers'
        report = self.report(activity=work)
        self.assertEqual(report['phase'], 'Choosing Encoder Layers')
        self.assertEqual([row['path'] for row in report['rows'] if row['current']], ['model.layers'])
        self.assertEqual(report['totals']['tokens'], 120)

    def test_unique_draft_waits_for_qwens_next_step_after_only_one_choice(self):
        self.draft.selections = ['gamma']
        self.draft.phase = 'reviewing'
        report = self.report()
        self.assertEqual(report['phase'], 'Choosing next step')
        self.assertIn('run it or change an unused setting', report['detail'])
        self.assertEqual(report['choices_selected'], 1)
        self.assertEqual([row['path'] for row in report['rows'] if row['current']], [REVISION_PARAMETER])

    def test_finished_run_is_distinct_from_comparison_and_analysis(self):
        self.draft.selections = PARAMETER_ORDER.copy()
        self.draft.phase = 'submitted'
        self.draft.run_id = str(uuid4())
        run = dict(status='completed', high_score=25)
        report = self.report(run=run)
        self.assertEqual(report['phase'], 'Comparing results')
        self.assertEqual(report['outcome'], 'Awaiting comparison')
        comparison = {'current_golden_run_id': self.draft.run_id}
        report = self.report(run=run, comparison=comparison)
        self.assertEqual(report['phase'], 'Recording results')
        self.assertEqual(report['analysis_status'], 'Recording')
        self.assertEqual(report['outcome'], 'New golden')
        self.assertEqual(report['target_score'], 20)
        self.assertEqual(report['difference'], 5)
        self.draft.phase = 'completed'
        report = self.report(run=run, comparison=comparison,
                             analysis=SimulationAnalysis(self.draft.run_id, self.draft.config, {}, 'Saved.'))
        self.assertEqual(report['phase'], 'Complete')
        self.assertEqual(report['analysis_status'], 'Saved')

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

    def test_seed_rotation_reports_baseline_work_and_completion_without_a_comparison(self):
        self.draft.phase = 'rotating_seed'
        self.assertEqual(self.report()['phase'], 'Rotating seed')
        self.draft.run_id = self.draft.golden_run_id
        self.draft.phase = 'submitted'
        run = dict(status='completed', high_score=5)
        self.golden['high_score'] = 5
        report = self.report(run=run)
        self.assertEqual(report['phase'], 'Recording results')
        self.assertEqual(report['outcome'], 'New golden baseline')
        self.draft.phase = 'completed'
        report = self.report(run=run, analysis=SimulationAnalysis(self.draft.run_id, self.draft.config, {}, None))
        self.assertEqual(report['phase'], 'Complete')
        self.assertEqual(report['outcome'], 'New golden baseline')

    def test_preparing_references_loads_measured_data_without_starting_choices(self):
        self.draft.phase = 'preparing'
        report = self.report()
        self.assertEqual(report['phase'], 'Preparing references')
        self.assertIn('Loading measured data', report['detail'])
        self.assertFalse(any(row['current'] for row in report['rows']))


class ExperimentStatusHttpTests(unittest.TestCase):
    def setUp(self):
        root = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.object(DAx3l, 'BASE_DIR', root))
        configuration_path = Path(root) / DAx3l.CONFIG_FILE
        configuration_path.parent.mkdir()
        configuration_path.write_text(json.dumps({'decision_grace_seconds': 90}))
        self.db = self.enterContext(patch('ax3l.server.ReportingServer.DbMgr')).return_value
        self.experiments = self.enterContext(patch('ax3l.server.ReportingServer.ExperimentDb')).return_value
        self.snake = self.enterContext(patch('ax3l.server.ReportingServer.SnakeLab')).return_value
        self.draft = ConfigurationDraft(str(uuid4()), str(uuid4()), {}, SimulationConfiguration.defaults())
        self.experiments.draft.return_value = self.draft
        self.experiments.last_completed_draft.return_value = None
        self.experiments.comparison.return_value = None
        self.experiments.analysis.return_value = None
        self.experiments.choice_events.return_value = []
        self.experiments.activity_events.return_value = []
        self.snake.get_run_result.return_value = dict(
            status='completed', high_score=0, config=deepcopy(self.draft.config))
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
        self.assertIn('Choosing a setting', page)
        self.assertIn('0 settings saved', page)
        self.assertEqual(page.count('type="checkbox" disabled'), 18)
        self.assertNotIn('>Pending</span>', page)
        self.assertNotIn('<td class="changed-value">', page)
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
        self.assertIn('Choosing a setting', self.get())
        page = self.get('/experiment-status?view=completed')
        self.assertIn('aria-current="page">Last completed</a>', page)
        self.assertIn('id="experiment-phase" aria-live="polite" aria-atomic="true">Complete</h2>', page)
        self.assertEqual(page.count('disabled checked'), 18)
        self.assertNotIn('>Pending</span>', page)
        self.assertNotIn('class="comparison-label"', page)
        self.assertIn('<dt>High score</dt><dd>0</dd>', page)
        self.assertIn('<dt>Difference</dt><dd>+0</dd>', page)
        self.assertIn('Golden retained', page)
        self.assertIn(f'href="/simulations/{completed.run_id}"', page)
        self.snake.get_run_result.assert_any_call(completed.golden_run_id)

    def test_inherited_column_precedes_chosen_values_and_only_changes_are_highlighted(self):
        self.snake.get_run_result.return_value['config']['model']['hidden_size'] = 96
        self.draft.config['model']['hidden_size'] = 96
        self.draft.config['model']['layers'] = 2
        self.draft.config['epsilon']['initial'] = 0.75
        self.draft.selections = ['hidden_size', 'layers', 'epsilon_pair']
        for view in ('current', 'completed'):
            with self.subTest(view=view):
                self.experiments.last_completed_draft.return_value = self.draft
                page = self.get('/experiment-status?view=' + view)
                self.assertIn('<th scope="col">Baseline</th><th scope="col">LLM Choice</th>', page)
                self.assertEqual(page.count('<td class="changed-value">'), 2)
                for path, inherited, chosen, changed in [
                    ('model.hidden_size', '96', '96', False),
                    ('model.layers', '1', '2', True),
                    ('epsilon.initial', str(self.snake.get_run_result.return_value['config']['epsilon']['initial']),
                     '0.75', True),
                    ('epsilon.decay', str(self.draft.config['epsilon']['decay']),
                     str(self.draft.config['epsilon']['decay']), False),
                ]:
                    row = page.split(f'data-parameter="{path}"', 1)[1].split('</tr>', 1)[0]
                    self.assertLess(row.index(f'class="inherited-value">{inherited}</td>'),
                                    row.index(f'class="parameter-value">{chosen}</span>'))
                    self.assertEqual('class="changed-value"' in row, changed)
                    self.assertNotIn('class="comparison-label"', row)
                pending = page.split('data-parameter="epsilon_nice.probability"', 1)[1].split('</tr>', 1)[0]
                self.assertIn('>—</span>', pending)
                self.assertNotIn('class="parameter-value"', pending)

    def test_countdown_box_precedes_the_table_and_refreshes_with_the_saved_timer(self):
        self.draft.decision_expires_at = 1000.5
        with patch('ax3l.activity.ExperimentStatus.time', return_value=900):
            page = self.get()
        self.assertLess(page.index('id="llm-countdown"'), page.index('<table class="status-checklist"'))
        self.assertIn('LLM countdown', page)
        self.assertEqual(json.loads(page.split("data-countdown='", 1)[1].split("'", 1)[0]),
                         dict(remaining_seconds=100.5, grace_seconds=90, expiry_action='reset'))
        self.draft.phase, self.draft.selections = 'reviewing', ['layers']
        with patch('ax3l.activity.ExperimentStatus.time', return_value=1030.5):
            page = self.get()
        self.assertEqual(json.loads(page.split("data-countdown='", 1)[1].split("'", 1)[0]),
                         dict(remaining_seconds=-30, grace_seconds=90, expiry_action='run'))
        self.draft.phase = 'ready'
        page = self.get()
        self.assertIn("data-countdown='null'", page)
        self.assertIn('>Not active</span>', page)

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

    def test_duplicate_draft_displays_revision_work_without_an_extra_configuration_checkbox(self):
        self.draft.phase = 'selecting_parameter'
        self.draft.selections = PARAMETER_ORDER.copy()
        page = self.get()
        self.assertIn('Choosing a setting to revise', page)
        self.assertIn('Experiment decision', page)
        self.assertIn('15 settings saved', page)
        self.assertEqual(page.count('disabled checked'), 18)
        self.assertNotIn('>Pending</span>', page)

    def test_setup_shows_live_steps_with_separate_turn_times_and_tokens(self):
        stamp = datetime(2026, 11, 15, 12)
        observed = stamp + timedelta(seconds=400)

        def event(event_id, name, seconds, *, parent=None, parameter=None, image=False, detail=None, reasoning=False):
            return dict(event_id=event_id, name=name, occurred_at=stamp + timedelta(seconds=seconds),
                        observed_at=observed, parent_event_id=parent, parameter=parameter,
                        has_image=image, has_reasoning=reasoning, detail=detail)

        self.draft.selections = PARAMETER_ORDER[:7]
        self.experiments.choice_events.return_value = [
            event(1, 'choice_chart_started', 0, parameter='epsilon_pair', detail='Score trends'),
            event(2, 'choice_chart_finished', 1, parameter='epsilon_pair', detail='Complete'),
            event(4, 'prompt_sent', 2, parent=3, parameter='epsilon_pair', image=True),
            event(5, 'llm_request_started', 3, parent=3),
            event(6, 'reply_received', 73, parent=3, reasoning=True,
                  detail=json.dumps(dict(prompt_tokens=1234, completion_tokens=321))),
            event(7, 'tool_execution_started', 74, parent=3, detail=json.dumps(dict(
                function=dict(name='data_tool', arguments=json.dumps(dict(url='/latest/scores')))))),
            event(8, 'tool_execution_completed', 74.05, parent=3, detail='ok'),
            event(9, 'llm_request_started', 75, parent=3),
            event(10, 'reply_received', 90, parent=3,
                  detail=json.dumps(dict(prompt_tokens=1350, completion_tokens=50))),
            event(11, 'llm_request_started', 100, parent=3),
        ]
        page = self.get()
        self.assertIn('class="choice-chart" href="/events/4"', page)
        self.assertIn('Render score trends chart', page)
        self.assertIn('<th scope="col">LLM details</th>', page)
        self.assertIn('href="/events/4" target="_blank" rel="noopener">Prompt</a>', page)
        self.assertIn('href="/events/6/reason" target="_blank" rel="noopener">Reasoning</a>', page)
        self.assertNotIn('href="/events/10/reason"', page)
        self.assertIn('Read data <a class="read-target" href="/tool-results/8">/latest/scores</a>', page)
        self.assertIn('class="item-elapsed">00:00</td>', page)
        self.assertIn('class="item-elapsed">01:10</td>', page)
        self.assertIn('class="item-elapsed">00:15</td>', page)
        self.assertIn('class="item-elapsed">05:00</td>', page)
        self.assertIn('>Running</td>', page)
        self.assertIn('>Input tokens</th>', page)
        self.assertIn('>Output tokens</th>', page)
        for count in ('1,234', '321', '1,350', '50'):
            self.assertEqual(page.count(f'class="item-tokens">{count}</td>'), 1)
        footer = page.split('<tfoot>')[1].split('</tfoot>')[0]
        self.assertIn('class="item-elapsed">06:26</td>', footer)
        self.assertIn('class="item-tokens">2,584</td>', footer)
        self.assertIn('class="item-tokens">371</td>', footer)
        self.assertIn('>Total tokens</th>', footer)
        self.assertIn('class="item-tokens" colspan="2">2,955</td>', footer)
        row = page.split('data-parameter="epsilon.decay"', 1)[1].split('</tr>', 1)[0]
        self.assertIn('class="item-elapsed"><strong>06:26</strong></td>', row)
        self.assertIn('class="item-tokens"><strong>2,584</strong></td>', row)
        self.assertIn('class="item-tokens"><strong>371</strong></td>', row)
        self.assertIn('aria-expanded="false"', row)
        self.assertIn('id="tasks-epsilon.decay" class="status-subtasks" hidden', page)
        empty_row = page.split('data-parameter="epsilon.initial"', 1)[1].split('</tr>', 1)[0]
        self.assertIn('class="item-elapsed"></td>', empty_row)
        self.assertEqual(empty_row.count('class="item-tokens"></td>'), 2)
        self.assertEqual(page.count('>Qwen request</th>'), 3)
        for recorded in self.experiments.choice_events.return_value:
            recorded['observed_at'] += timedelta(seconds=5)
        page = self.get()
        self.assertIn('class="item-elapsed">06:31</td>', page)
        row = page.split('data-parameter="epsilon.decay"', 1)[1].split('</tr>', 1)[0]
        self.assertIn('class="item-elapsed"><strong>06:31</strong></td>', row)
        self.experiments.choice_events.return_value.append(
            event(12, 'reply_received', 405, parent=3,
                  detail=json.dumps(dict(prompt_tokens=2000, completion_tokens=400))))
        page = self.get()
        footer = page.split('<tfoot>')[1].split('</tfoot>')[0]
        self.assertIn('class="item-elapsed">06:31</td>', footer)
        self.assertIn('class="item-tokens">4,584</td>', footer)
        self.assertIn('class="item-tokens">771</td>', footer)
        self.assertIn('class="item-tokens" colspan="2">5,355</td>', footer)
        row = page.split('data-parameter="epsilon.decay"', 1)[1].split('</tr>', 1)[0]
        self.assertIn('class="item-tokens"><strong>4,584</strong></td>', row)
        self.assertIn('class="item-tokens"><strong>771</strong></td>', row)
        for recorded in self.experiments.choice_events.return_value:
            recorded['observed_at'] += timedelta(seconds=5)
        self.assertIn('class="item-elapsed">06:31</td>', self.get())

    def test_followup_prompts_and_reasoning_are_linked_to_their_exact_events(self):
        stamp = datetime(2026, 11, 16, 12)

        def event(event_id, name, parameter=None, reasoning=False, detail=None):
            return dict(event_id=event_id, name=name, occurred_at=stamp, observed_at=stamp,
                        parent_event_id=1, parameter=parameter, has_image=False,
                        has_reasoning=reasoning, detail=detail)

        self.experiments.choice_events.return_value = [
            event(2, 'prompt_sent', parameter='revision'),
            event(3, 'llm_request_started'),
            event(4, 'reply_received', reasoning=True, detail='{"prompt_tokens":10,"completion_tokens":2}'),
            event(5, 'prompt_sent'),
            event(6, 'llm_request_started'),
            event(7, 'reply_received', detail='{"prompt_tokens":12,"completion_tokens":3}'),
            event(8, 'prompt_sent'),
            event(9, 'llm_request_started'),
        ]
        page = self.get()
        for prompt in (2, 5, 8):
            self.assertIn(f'href="/events/{prompt}" target="_blank" rel="noopener">Prompt</a>', page)
        self.assertEqual(page.count('>Prompt sent</th>'), 3)
        self.assertEqual(page.count('>Reasoning</a>'), 1)
        self.assertIn('href="/events/4/reason"', page)
        self.assertNotIn('href="/events/7/reason"', page)
        self.assertNotIn('href="/events/9/reason"', page)
        self.assertIn('class="item-tokens">22</td>', page)
        self.assertIn('class="item-tokens">5</td>', page)
        event_log = self.enterContext(patch('ax3l.server.ReportingServer.EventLogDb')).return_value
        event_log.get.return_value = dict(event_id=4, category='Conversation', name='reply_received',
            content=json.dumps(dict(choices=[dict(message=dict(reasoning_content='Compare loss <script>carefully</script>.'))])))
        reasoning = self.get('/events/4/reason')
        self.assertIn('Compare loss &lt;script&gt;carefully&lt;/script&gt;.', reasoning)

    def test_read_targets_link_each_specific_result_and_include_guides_and_failures(self):
        stamp = datetime(2026, 11, 16, 12)

        def event(event_id, name, detail=None, parameter=None):
            return dict(event_id=event_id, name=name, occurred_at=stamp, observed_at=stamp,
                        parent_event_id=1, parameter=parameter, has_image=False, has_reasoning=False, detail=detail)

        events = [event(2, 'prompt_sent', parameter='revision')]
        for start, name, path, end, status in (
                (3, 'data_tool', '/draft', 4, 'ok'), (5, 'data_tool', '/', 6, 'ok'),
                (7, 'data_tool', '/golden/model', 8, 'ok'), (9, 'kb_tool', '/', 10, 'ok'),
                (11, 'data_tool', '/missing', 12, 'rejected'), (13, 'data_tool', '/draft', 14, 'failed')):
            events.extend([
                event(start, 'tool_execution_started', json.dumps(dict(function=dict(
                    name=name, arguments=json.dumps(dict(url=path)))))),
                event(end, 'tool_execution_failed' if status == 'failed' else 'tool_execution_completed', status),
            ])
        self.experiments.choice_events.return_value = events
        page = self.get()
        for result, path in ((4, '/draft'), (6, '/'), (8, '/golden/model'), (10, '/'), (12, '/missing'), (14, '/draft')):
            self.assertIn(f'href="/tool-results/{result}">{path}</a>', page)
        self.assertIn('Read guide <a', page)
        events.append(event(15, 'tool_execution_started', json.dumps(dict(function=dict(
            name='data_tool', arguments=json.dumps(dict(url='/draft')))))))
        pending = self.get().split('>Read data', 1)[1]
        self.assertNotIn('href="/tool-results/15"', pending)

    def test_prompt_and_reasoning_previews_use_the_shared_parser_and_preserve_original_pages(self):
        event_log = self.enterContext(patch('ax3l.server.ReportingServer.EventLogDb')).return_value
        text = '# Evidence\n\nCompare **settings**.\n\n```json\n{"learning_rate":0.0005}\n```\n<script>alert(1)</script>'
        image = 'data:image/png;base64,cG5n'
        event_log.get.return_value = dict(event_id=81, category='Conversation', name='prompt_sent',
            content=json.dumps(dict(role='user', content=[dict(type='text', text=text),
                dict(type='image_url', image_url=dict(url=image))])))
        original = self.get('/events/81')
        self.assertIn('```json', original)
        prompt = self.get('/events/81?preview=1')
        self.assertIn('id="message-content" class="tool-result"', prompt)
        self.assertIn('<strong>settings</strong>', prompt)
        self.assertIn('<td>learning rate</td>', prompt)
        self.assertIn('<td>0.0005</td>', prompt)
        self.assertIn(f'<img src="{image}"', prompt)
        self.assertNotIn('```json', prompt)
        self.assertNotIn('<script>', prompt)
        event_log.get.return_value = dict(event_id=82, category='Conversation', name='reply_received',
            content=json.dumps(dict(choices=[dict(message=dict(reasoning_content=text, content='Assistant answer'))])))
        reasoning = self.get('/events/82/reason?preview=1')
        self.assertIn('<td>learning rate</td>', reasoning)
        self.assertIn('<strong>settings</strong>', reasoning)
        self.assertNotIn('Assistant answer', reasoning)
        self.assertNotIn('<script>', reasoning)
        self.assertIn('```json', self.get('/events/82/reason'))

    def test_recorded_result_endpoint_formats_json_and_rejects_unrelated_events(self):
        event_log = self.enterContext(patch('ax3l.server.ReportingServer.EventLogDb')).return_value
        event = dict(event_id=8, category='Tool', name='tool_execution_completed',
                     content=json.dumps(dict(status='ok', page=json.dumps(dict(high_score=38, zero=0)))))
        event_log.get.return_value = event
        page = self.get('/tool-results/8')
        self.assertIn('Tool result #8', page)
        self.assertIn('<td>high score</td>', page)
        self.assertIn('<td>38</td>', page)
        self.snake.get_run_result.assert_not_called()
        event_log.get.assert_called_once_with(8)
        for record in (None, dict(event, category='Conversation'), dict(event, name='tool_execution_started')):
            with self.subTest(record=record):
                event_log.get.return_value = record
                with self.assertRaises(HTTPError) as error:
                    self.get('/tool-results/8')
                self.assertEqual(error.exception.code, 404)
        self.db.close.reset_mock()
        event_log.get.side_effect = RuntimeError('database unavailable')
        with patch('ax3l.server.ReportingServer.traceback.print_exc'), self.assertRaises(HTTPError) as error:
            self.get('/tool-results/8')
        self.assertEqual(error.exception.code, 500)
        self.db.close.assert_called_once()

    def test_image_endpoint_returns_latest_exact_png_and_missing_images_are_unlinked(self):
        run_id = str(uuid4())
        stamp = datetime(2026, 11, 15, 12)
        self.experiments.activity_events.return_value = [
            dict(event_id=1, process_id=run_id, name='simulation_analysis_task',
                 occurred_at=stamp, observed_at=stamp, parent_event_id=None,
                 task=dict(section='scores', phase='preparing')),
            dict(event_id=2, process_id=run_id, name='conversation_started',
                 occurred_at=stamp, parent_event_id=None),
            dict(event_id=3, process_id=run_id, name='prompt_sent', parameter='simulation_summary',
                 occurred_at=stamp, parent_event_id=2, source_name='AnalyzeSimulation'),
        ]
        event_log = self.enterContext(patch('ax3l.server.ReportingServer.EventLogDb')).return_value
        event_log.get.return_value = dict(content=json.dumps(dict(content=[
            dict(type='image_url', image_url=dict(url='data:image/png;base64,cG5n'))])))
        with urlopen(f'{self.base}/analysis-images/{run_id}/scores.png') as response:
            self.assertEqual(response.headers['Content-Type'], 'image/png')
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertEqual(response.read(), b'png')
        event_log.get.assert_called_once_with(3)
        for path in (f'/analysis-images/{run_id}/loss.png',
                     f'/analysis-images/{run_id}/other.png', '/analysis-images/invalid/scores.png'):
            with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                self.get(path)
            self.assertEqual(error.exception.code, 404)


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
