"""Exercise the active experiment, its two conversations, and persisted links."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import json
import os
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from ax3l.activity.ViewConfiguration import apply_values
from ax3l.entities.ExperimentState import ExperimentState
from ax3l.entities.ExperimentView import VIEWS
from ax3l.entities.ViewProposal import ViewProposal
from ax3l.interface.database.DbMgr import DbMgr
from ax3l.interface.database.EventLogDb import EventLogDb
from ax3l.interface.database.ExperimentDb import ExperimentDb
from ax3l.interface.database.ExperimentStatusDb import ExperimentStatusDb
from ax3l.interface.SimulationConfiguration import SimulationConfiguration
from ax3l.presentation.reporting.ExperimentStatus import experiment_sections, experiment_summary, experiment_totals
from ax3l.presentation.reporting.ReportRenderer import ReportRenderer


def conversation(process, name, stage, start=10, accepted=True, error=None, ended=True):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = []
    def event(category, name, content, **fields):
        row = dict(event_id=start + len(rows), occurred_at=now + timedelta(seconds=len(rows)),
                   observed_at=now + timedelta(seconds=5),
                   name=name, category=category, log_level='INFO', process_id=process,
                   parent_event_id=start - 1, parameter=parameter, content=content,
                   prompt_type=None, source_name=stage)
        row.update(fields)
        rows.append(row)
    parameter = name
    event('Conversation', 'prompt_sent', None, prompt_type='ARRAY' if stage == 'evaluation' else 'STRING')
    event('LLM', 'llm_request_started', 'Request started.')
    arguments = dict(observations='Measured results support the hypothesis.') if stage == 'evaluation' else dict(
        hypothesis='A stronger food reward should increase the high score.', values={'game.rewards.food': 12})
    event('Conversation', 'reply_received', json.dumps(dict(
        choices=[dict(message=dict(reasoning_content='Recorded reasoning.', tool_calls=[]))],
        usage=dict(prompt_tokens=2241, completion_tokens=578))))
    if accepted:
        event('Tool', 'tool_execution_completed', json.dumps(dict(status='accepted', **arguments)))
    if ended:
        event('Conversation', 'conversation_ended', error or 'View submission accepted.')
        if error:
            rows[-1]['log_level'] = 'ERROR'
    return rows


def status_data(name='reward-signals', phase='choosing'):
    baseline = SimulationConfiguration.defaults()
    order = list(reversed(VIEWS))
    state = ExperimentState('selection-cycle', phase, deepcopy(baseline), order=order,
                            view_index=order.index(name), golden_run_id='baseline-run',
                            reference_run_id='baseline-run', latest_run_id='baseline-run')
    return dict(state=state, events=[], selection_config=baseline, reference_config=baseline,
                latest_config=None, reference_run=dict(status='completed', high_score=10, config=baseline),
                candidate_run=None)


def complete_candidate(data, score=12, phase='evaluating'):
    state = data['state']
    state.phase, state.run_id, state.latest_run_id = phase, 'candidate-run', 'candidate-run'
    state.golden_run_id = 'candidate-run' if score >= 10 else 'baseline-run'
    state.config = apply_values(data['selection_config'], {'game.rewards.food': 12})
    data.update(candidate_run=dict(status='completed', high_score=score, config=state.config),
                latest_config=state.config)


def render_status(data):
    return ReportRenderer().recent(dict(
        experiment=data, events=[], current_run=None, current_board_gif_url=None,
        snake_lab_status='Idle', high_score=None, all_time_high_score=None,
        experiment_cycles=0, simulations_submitted=0, games_played=0, moves_made=0,
    )).decode()


class PanelParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.panels, self.links = [], []
        self.summaries, self.totals, self.tables = [], [], []
        self._text = None
        self._view_table = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'details' and attrs.get('class') == 'view-section':
            self.panels.append(attrs)
        if tag == 'a':
            self.links.append(attrs['href'])
        if tag == 'summary':
            self.summaries.append([])
            self._text = self.summaries[-1]
        if tag == 'div' and attrs.get('id') == 'experiment-totals':
            self._text = self.totals
        if tag == 'table' and 'view-table' in attrs.get('class', '').split():
            self._view_table = True
            self.tables.append([])
        if self._view_table:
            if tag == 'tr':
                self.tables[-1].append([])
            elif tag in ('td', 'th'):
                self.tables[-1][-1].append(tag)

    def handle_endtag(self, tag):
        if tag == 'summary' or (tag == 'div' and self._text is self.totals):
            self._text = None
        if tag == 'table':
            self._view_table = False

    def handle_data(self, data):
        if self._text is not None:
            self._text.append(data)


class ExperimentStatusTests(unittest.TestCase):
    def test_two_sections_follow_the_flow_and_retain_conversation_details(self):
        data = status_data()
        complete_candidate(data, phase='completed')
        data['state'].proposals['reward-signals'] = ViewProposal('Current tested hypothesis.', {})
        data['events'] = (conversation('selection-cycle', 'reward-signals', 'selection') +
                          conversation('selection-cycle', 'reward-signals', 'evaluation', start=30))
        sections = experiment_sections(data)
        self.assertEqual([section['id'] for section in sections],
                         ['selection-reward-signals', 'evaluation-reward-signals'])
        selection, evaluation = sections
        self.assertEqual((selection['prompt_id'], evaluation['prompt_id']), (10, 30))
        self.assertEqual(selection['elapsed'], '00:03')
        self.assertEqual((selection['input_tokens'], selection['output_tokens']), (2241, 578))
        self.assertEqual(selection['rows'][0]['baseline'], '10')
        self.assertEqual(selection['rows'][0]['choice'], '12')
        self.assertTrue(selection['rows'][0]['saved'])
        self.assertTrue(selection['rows'][0]['changed'])
        self.assertFalse(selection['rows'][1]['saved'])
        self.assertEqual(evaluation['observations'], 'Measured results support the hypothesis.')
        html = render_status(data)
        parsed = PanelParser(html)
        self.assertEqual(len(parsed.panels), 2)
        for link in ('/events/10', '/events/30', '/events/12', '/events/12/reason',
                     '/simulations/baseline-run', '/simulations/candidate-run'):
            self.assertIn(link, parsed.links)
        positions = [html.index(marker) for marker in (
            'id="selection-reward-signals"', 'id="simulation-status-title"', 'id="evaluation-reward-signals"')]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(html.count('>Baseline</th>'), 2)
        for heading in ('Saved', 'Setting or step', 'LLM details', 'LLM choice',
                        'Configuration Setting', 'Latest'):
            self.assertEqual(html.count(f'>{heading}</th>'), 1)
        for table, section in zip(parsed.tables, sections):
            evaluation_stage = section['stage'] == 'evaluation'
            self.assertTrue(all(len(row) == (3 if evaluation_stage else 5) for row in table))
            self.assertEqual(len(table), len(section['rows']) + (1 if evaluation_stage else 2))
        evaluation_html = html.split('id="evaluation-reward-signals"', 1)[1].split('</details>', 1)[0]
        positions = [evaluation_html.index(text) for text in (
            '<strong>Hypothesis:</strong>', '<strong>Observations:</strong>',
            'Measured results support the hypothesis.', '<a href="/events/32/reason">Reasoning</a>',
            '<a href="/events/32">Response (details)</a>', '<table')]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn('Measured results support the hypothesis.', evaluation_html.split('<table', 1)[1])
        self.assertIn('Reward Signals Selection: Elapsed (00:03), tokens in (2,241), tokens out (578)',
                      ''.join(parsed.summaries[0]))
        self.assertEqual(''.join(parsed.totals).strip(),
                         'Totals: Elapsed (00:06), tokens in (4,482), tokens out (1,156)')
        self.assertIn('Food Reward', html)
        self.assertIn('Reward for eating food.', html)
        self.assertIn('viewStatus.replaceChildren', html)
        self.assertIn('section.open = saved.open', html)
        self.assertIn('data-experiment-id="selection-cycle"', html)
        self.assertIn('viewState.get(`${section.dataset.experimentId}:${section.id}`)', html)

    def test_totals_combine_only_the_active_experiments_two_conversations(self):
        data = status_data()
        data['events'] = (conversation('selection-cycle', 'reward-signals', 'selection') +
                          conversation('selection-cycle', 'reward-signals', 'evaluation', start=30,
                                       accepted=False, ended=False) +
                          conversation('selection-cycle', 'architecture', 'selection', start=50) +
                          conversation('older-cycle', 'reward-signals', 'evaluation', start=70))
        active = data['events'][6:8]
        for event in active:
            event['observed_at'] = active[0]['occurred_at'] + timedelta(seconds=63)
        self.assertEqual(experiment_totals(experiment_sections(data)),
                         dict(elapsed='01:06', input_tokens=4482, output_tokens=1156))
        self.assertEqual(len(PanelParser(render_status(data)).panels), 2)

    def test_totals_preserve_missing_metrics_and_measured_zero_usage(self):
        data = status_data('training')
        self.assertEqual(experiment_totals(experiment_sections(data)),
                         dict(elapsed='—', input_tokens=None, output_tokens=None))
        data['events'] = conversation('selection-cycle', 'training', 'selection')
        response = json.loads(data['events'][2]['content'])
        response['usage'] = dict(prompt_tokens=0)
        data['events'][2]['content'] = json.dumps(response)
        self.assertEqual(experiment_totals(experiment_sections(data)),
                         dict(elapsed='00:03', input_tokens=0, output_tokens=None))

    def test_each_view_has_only_its_own_selection_and_evaluation(self):
        for name in VIEWS:
            with self.subTest(name=name):
                data = status_data(name)
                sections = experiment_sections(data)
                self.assertEqual([section['id'] for section in sections],
                                 [f'selection-{name}', f'evaluation-{name}'])
                self.assertEqual(sections[1]['status'], 'Awaiting simulation results')
                self.assertTrue(all(row['choice'] == '—' for row in sections[1]['rows']))
                self.assertEqual(len(PanelParser(render_status(data)).panels), 2)

    def test_evaluation_shows_the_active_views_proposal(self):
        data = status_data()
        data['state'].proposals = {'reward-signals': ViewProposal('Current tested hypothesis.', {})}
        self.assertEqual(experiment_sections(data)[1]['hypothesis'], 'Current tested hypothesis.')
        self.assertIsNone(experiment_sections(data)[0]['hypothesis'])

    def test_active_elapsed_uses_database_clock_without_adding_the_utc_offset(self):
        data = status_data(phase='evaluating')
        data['events'] = conversation('selection-cycle', 'reward-signals', 'evaluation',
                                      accepted=False, ended=False)
        started = datetime(2026, 11, 26, 12, 0, 0)
        observed = started + timedelta(minutes=4, seconds=6)
        for event in data['events']:
            event['occurred_at'], event['observed_at'] = started, observed
        section = experiment_sections(data)[1]
        self.assertEqual(section['status'], 'In progress')
        self.assertEqual(section['elapsed'], '04:06')
        self.assertIn('<strong>Observations:</strong> In progress', render_status(data))

    def test_completed_elapsed_uses_the_recorded_end_time(self):
        data = status_data()
        data['events'] = conversation('selection-cycle', 'reward-signals', 'evaluation')
        for event in data['events']:
            event['observed_at'] += timedelta(hours=5)
        self.assertEqual(experiment_sections(data)[1]['elapsed'], '00:03')

    def test_pending_active_failed_and_retried_conversations_are_distinguished(self):
        data = status_data('training')
        self.assertEqual(experiment_sections(data)[0]['status'], 'Waiting')
        data['events'] = conversation('selection-cycle', 'training', 'selection', accepted=False, ended=False)
        section = experiment_sections(data)[0]
        self.assertEqual(section['status'], 'In progress')
        self.assertTrue(section['open'])
        data['events'] = conversation('selection-cycle', 'training', 'selection', accepted=False,
                                      error='<script>Rejected values</script>')
        html = render_status(data)
        self.assertIn('Selection failed', html)
        self.assertIn('&lt;script&gt;Rejected values&lt;/script&gt;', html)
        self.assertNotIn('<script>Rejected', html)
        data['events'] += conversation('selection-cycle', 'training', 'selection', start=30)
        section = experiment_sections(data)[0]
        self.assertEqual(section['status'], 'Saved')
        self.assertEqual(section['prompt_id'], 30)
        self.assertEqual(len(PanelParser(render_status(data)).panels), 2)

    def test_duplicate_revisions_reuse_the_selection_panel(self):
        data = status_data(phase='revising')
        data['events'] = conversation('selection-cycle', 'reward-signals', 'selection')
        self.assertEqual(experiment_sections(data)[0]['status'], 'Revision required')
        self.assertIn('Revising duplicate configuration', render_status(data))
        data['events'] += conversation('selection-cycle', 'reward-signals', 'selection', start=30,
                                       accepted=False, ended=False)
        selection, evaluation = experiment_sections(data)
        self.assertEqual((selection['prompt_id'], selection['status']), (30, 'In progress'))
        self.assertIsNone(evaluation['prompt_id'])
        self.assertEqual(len(PanelParser(render_status(data)).panels), 2)

    def test_uninitialized_and_baseline_runs_have_no_prompt_panels(self):
        empty = dict(state=None, events=[], selection_config=None, reference_config=None,
                     latest_config=None, reference_run=None, candidate_run=None)
        html = render_status(empty)
        self.assertEqual(len(PanelParser(html).panels), 0)
        self.assertIn('Waiting for initialization', html)
        for field, title in (('baseline', 'Default baseline'), ('seed_baseline', 'Seed rotation baseline')):
            with self.subTest(field=field):
                data = status_data()
                setattr(data['state'], field, True)
                data['state'].order = []
                html = render_status(data)
                self.assertEqual(len(PanelParser(html).panels), 0)
                self.assertIn(title, html)
                self.assertIn('Baseline simulation', html)
                self.assertNotIn('Prompt not sent yet.', html)
                complete_candidate(data, phase='completed')
                self.assertIn('Golden baseline established.', render_status(data))

    def test_summary_shows_view_phase_seed_and_loss_count(self):
        data = status_data('exploration', 'running')
        data['state'].failures = 15
        summary = experiment_summary(data, experiment_sections(data))
        self.assertEqual(summary['title'], 'Exploration')
        self.assertEqual(summary['phase'], 'Running simulation')
        self.assertEqual(summary['seed'], data['state'].config['seed'])
        self.assertIn('Consecutive losses: 15 / 16', render_status(data))
        for phase, label in (('ready', 'Ready to submit simulation'), ('submitting', 'Submitting simulation'),
                             ('comparing', 'Comparing results'), ('evaluating', 'Evaluating results'),
                             ('completed', 'Completed')):
            data['state'].phase = phase
            self.assertEqual(experiment_summary(data, experiment_sections(data))['phase'], label)

    def test_simulation_outcome_distinguishes_promotion_tie_and_loss(self):
        for score, outcome in ((12, 'Promoted to golden.'), (10, 'Promoted to golden (tie).'),
                               (9, 'Golden retained.')):
            with self.subTest(score=score):
                data = status_data()
                complete_candidate(data, score)
                summary = experiment_summary(data, experiment_sections(data))
                self.assertEqual(summary['simulation']['outcome'], outcome)
                self.assertEqual(summary['simulation']['reference_score'], 10)
                self.assertEqual(summary['simulation']['candidate_score'], score)
                self.assertIn(outcome, render_status(data))
                data['state'].phase = 'comparing'
                self.assertIn('Awaiting comparison.', render_status(data))

    def test_running_and_terminal_simulation_states_use_the_recorded_run(self):
        data = status_data(phase='running')
        data['state'].run_id = 'candidate-run'
        for status in ('queued', 'running', 'paused', 'cancelling', 'failed', 'cancelled', 'completed'):
            with self.subTest(status=status):
                data['candidate_run'] = dict(status=status, high_score=12, config=data['state'].config)
                summary = experiment_summary(data, experiment_sections(data))
                self.assertEqual(summary['simulation']['status'], status.capitalize())
                self.assertEqual(summary['simulation']['candidate_score'], 12 if status == 'completed' else None)
                if status in ('failed', 'cancelled'):
                    self.assertEqual(summary['phase'], f'Simulation {status}')
                    self.assertIn('Experiment stopped before comparison.', render_status(data))
                elif status == 'completed':
                    self.assertEqual(summary['phase'], 'Awaiting comparison')

    def test_invalid_response_is_reported_as_failure_with_missing_usage(self):
        data = status_data('training')
        data['events'] = conversation('selection-cycle', 'training', 'selection', accepted=False, error='Invalid JSON')
        data['events'][2]['content'] = 'Invalid JSON response'
        section = experiment_sections(data)[0]
        self.assertEqual(section['status'], 'Failed')
        self.assertIsNone(section['input_tokens'])
        self.assertIn('Invalid JSON', render_status(data))
        renderer = ReportRenderer()
        for content in ('<script>Invalid JSON response</script>', '[]', '{"error":"Rejected"}'):
            event = dict(event_id=99, category='Conversation', name='reply_received', content=content)
            html = renderer.event(event).decode()
            self.assertIn('Reply #99', html)
            self.assertNotIn('<script>Invalid', html)

    def test_reporting_reads_the_candidate_run_instead_of_the_previous_latest(self):
        from ax3l.app.reporting.Reports import Reports

        data = status_data(phase='running')
        data['state'].run_id = 'candidate-run'
        snake, background = Mock(), Mock()
        runs = {'baseline-run': data['reference_run'],
                'candidate-run': dict(status='running', high_score=None, config=data['state'].config)}
        snake.get_run_result.side_effect = runs.__getitem__
        background.status.return_value = dict(snake_lab_status='Running Simulation', all_time_high_score=10)
        background.episode_totals.return_value = {}
        with patch('ax3l.app.reporting.Reports.DbMgr'), patch('ax3l.app.reporting.Reports.EventLogDb') as log, \
                patch('ax3l.app.reporting.Reports.ExperimentStatusDb') as status:
            log.return_value.recent.return_value = []
            log.return_value.current_golden_config.return_value = None
            status.return_value.read.return_value = data
            result = Reports(snake, background, Mock()).recent()['experiment']
        self.assertEqual(result['candidate_run'], runs['candidate-run'])
        self.assertEqual(result['reference_run'], runs['baseline-run'])
        self.assertEqual(snake.get_run_result.call_count, 2)
        snake.get_config.assert_not_called()


@unittest.skipUnless(os.environ.get('AX3L_TEST_DB') == '1', 'requires disposable MariaDB test database')
class ExperimentStatusDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ['DB_NAME'], 'ax3l_test')
        self.db = DbMgr()
        self.addCleanup(self.db.close)
        self.ids = [str(uuid4()), str(uuid4())]
        self.addCleanup(self.clean)
        self.log = EventLogDb(self.db)

    def clean(self):
        for process in reversed(self.ids):
            self.db.execute('DELETE FROM events WHERE process_id=%s ORDER BY event_id DESC', (process,))

    def record(self, process, name, stage):
        rows = conversation(process, name, stage)
        parent = self.log.log('conversation_started', 'Conversation', 'INFO', 'View conversation.', process_id=process)
        for row in rows:
            content = row['content']
            if row['name'] == 'prompt_sent':
                content = json.dumps(dict(role='user', content=[dict(type='text', text='Evaluation'),
                    dict(type='image_url', image_url=dict(url='data:image/png;base64,LARGE_IMAGE'))]
                    ))
            self.log.log(row['name'], row['category'], row['log_level'], content,
                         process_id=process, parent_event_id=parent, parameter=name, source_name=stage)

    def test_current_experiment_uses_explicit_stages_for_multimodal_prompts(self):
        first, second = self.ids
        config = SimulationConfiguration.defaults()
        ExperimentDb(self.db).save(ExperimentState(first, 'completed', deepcopy(config)))
        self.record(first, 'architecture', 'evaluation')
        state = ExperimentState(second, 'choosing', deepcopy(config), order=list(VIEWS))
        ExperimentDb(self.db).save(state)
        self.record(second, 'reward-signals', 'selection')
        self.record(second, 'reward-signals', 'evaluation')
        self.record(second, 'architecture', 'selection')
        state.config['game']['rewards']['food'] = 12
        ExperimentDb(self.db).save(state)
        data = ExperimentStatusDb(self.db).read()
        self.assertEqual(data['state'], state)
        self.assertEqual(data['selection_config']['game']['rewards']['food'], 10)
        self.assertTrue(all('LARGE_IMAGE' not in (event['content'] or '') for event in data['events']))
        self.assertTrue(all(event['parameter'] == 'reward-signals' for event in data['events']))
        data.update(reference_config=config, latest_config=state.config)
        sections = {s['id']: s for s in experiment_sections(data)}
        self.assertEqual(sections['evaluation-reward-signals']['status'], 'Saved')
        self.assertEqual(sections['selection-reward-signals']['status'], 'Saved')
        self.assertEqual(len(sections), 2)
        self.assertNotIn('evaluation-architecture', sections)

    def test_baseline_reads_do_not_require_an_active_view_or_conversations(self):
        for process, field in zip(self.ids, ('baseline', 'seed_baseline')):
            with self.subTest(field=field):
                state = ExperimentState(process, 'running', SimulationConfiguration.defaults(), **{field: True})
                ExperimentDb(self.db).save(state)
                self.record(process, 'reward-signals', 'selection')
                data = ExperimentStatusDb(self.db).read()
                self.assertEqual(data['state'], state)
                self.assertEqual(data['events'], [])
                self.assertIsNone(data['selection_config'])
                self.assertEqual(experiment_sections(data), [])

    def test_active_elapsed_uses_mariadb_time_in_a_non_utc_session(self):
        self.db.execute("SET time_zone = '-05:00'")
        frozen = int(datetime(2026, 11, 26, 17, 4, 6, tzinfo=timezone.utc).timestamp())
        self.db.execute('SET timestamp = %s', (frozen,))
        process = self.ids[0]
        config = SimulationConfiguration.defaults()
        ExperimentDb(self.db).save(ExperimentState(process, 'evaluating', config, order=list(VIEWS)))
        parent = self.log.log('conversation_started', 'Conversation', 'INFO', 'Evaluating.', process_id=process)
        self.log.log('prompt_sent', 'Conversation', 'INFO', json.dumps(dict(role='user', content=[
            dict(type='text', text='Evaluate results.')])), process_id=process,
            parent_event_id=parent, parameter='reward-signals', source_name='evaluation')
        request = self.log.log('llm_request_started', 'LLM', 'INFO', 'Evaluating.', process_id=process,
                               parent_event_id=parent, parameter='reward-signals', source_name='evaluation')
        self.db.execute('''UPDATE events SET occurred_at = CURRENT_TIMESTAMP(6) - INTERVAL 246 SECOND
                           WHERE event_id = %s''', (request,))
        data = ExperimentStatusDb(self.db).read()
        data.update(reference_config=config, latest_config=config)
        section = experiment_sections(data)[1]
        self.assertEqual(section['status'], 'In progress')
        self.assertEqual(section['elapsed'], '04:06')
