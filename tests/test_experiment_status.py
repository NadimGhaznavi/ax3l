"""Exercise eight view panels and their persisted conversation links."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import json
import os
import unittest
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
from ax3l.presentation.reporting.ExperimentStatus import experiment_sections, experiment_totals
from ax3l.presentation.reporting.ReportRenderer import ReportRenderer


def conversation(process, name, stage, start=10, accepted=True, error=None, ended=True):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = []
    def event(category, name, content, **fields):
        row = dict(event_id=start + len(rows), occurred_at=now + timedelta(seconds=len(rows)),
                   observed_at=now + timedelta(seconds=5),
                   name=name, category=category, log_level='INFO', process_id=process,
                   parent_event_id=start - 1, parameter=parameter, content=content,
                   prompt_type=None)
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


def status_data():
    baseline = SimulationConfiguration.defaults()
    state = ExperimentState('selection-cycle', 'choosing', deepcopy(baseline), order=list(reversed(VIEWS)),
                            previous={name: ViewProposal('Previous tested hypothesis.', {}) for name in VIEWS},
                            observations={name: 'Previous observations.' for name in VIEWS})
    return dict(state=state, events=[], selection_config=baseline, reference_config=baseline,
                latest_config=apply_values(baseline, {'game.rewards.food': 12}), evaluation_id='evaluation-cycle')


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
    def test_eight_sections_retain_headers_descriptions_and_conversation_costs_once(self):
        data = status_data()
        data['events'] = (conversation('evaluation-cycle', 'reward-signals', 'evaluation') +
                          conversation('selection-cycle', 'reward-signals', 'selection', start=30))
        sections = experiment_sections(data)
        self.assertEqual(len(sections), 8)
        self.assertEqual([section['id'] for section in sections[:4]], [f'evaluation-{name}' for name in VIEWS])
        self.assertEqual([section['id'] for section in sections[4:]], [f'selection-{name}' for name in reversed(VIEWS)])
        evaluation = sections[0]
        selection = sections[-1]
        self.assertEqual((evaluation['prompt_id'], selection['prompt_id']), (10, 30))
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
        self.assertEqual(len(parsed.panels), 8)
        self.assertIn('/events/10', parsed.links)
        self.assertIn('/events/30', parsed.links)
        self.assertIn('/events/32', parsed.links)
        self.assertIn('/events/32/reason', parsed.links)
        self.assertEqual(html.count('>Baseline</th>'), 8)
        for heading in ('Saved', 'Setting or step', 'LLM details', 'LLM choice',
                        'Configuration Setting', 'Latest'):
            self.assertEqual(html.count(f'>{heading}</th>'), 4)
        for heading in ('Elapsed', 'Input tokens', 'Output tokens'):
            self.assertNotIn(f'>{heading}</th>', html)
        self.assertEqual(len(parsed.tables), 8)
        for table, section in zip(parsed.tables, sections):
            evaluation = section['stage'] == 'evaluation'
            self.assertTrue(all(len(row) == (3 if evaluation else 5) for row in table))
            self.assertEqual(len(table), len(section['rows']) + (1 if evaluation else 2))
        evaluation_html = html.split('id="evaluation-reward-signals"', 1)[1].split('</details>', 1)[0]
        expected_order = ('<strong>Hypothesis:</strong>', '<strong>Observations:</strong>',
                          'Measured results support the hypothesis.',
                          '<a href="/events/12/reason">Reasoning</a>',
                          '<a href="/events/12">Response (details)</a>', '<table')
        positions = [evaluation_html.index(text) for text in expected_order]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn('Measured results support the hypothesis.', evaluation_html.split('<table', 1)[1])
        self.assertNotIn('view-conversation', evaluation_html)
        self.assertNotIn('Evaluate results', html)
        self.assertIn('Reward Signals Evaluation: Elapsed (00:03), tokens in (2,241), tokens out (578)',
                      ''.join(parsed.summaries[0]))
        self.assertEqual(''.join(parsed.totals).strip(),
                         'Totals: Elapsed (00:06), tokens in (4,482), tokens out (1,156)')
        self.assertIn('Food Reward', html)
        self.assertIn('Reward for eating food.', html)
        self.assertEqual(html.count('2,241'), 2)
        self.assertIn('viewStatus.replaceChildren', html)
        self.assertIn('section.open = saved.open', html)

    def test_totals_combine_all_eight_sections_including_active_elapsed(self):
        data = status_data()
        data['events'] = []
        for index, (stage, name) in enumerate((stage, name) for stage in ('evaluation', 'selection')
                                             for name in VIEWS):
            events = conversation(data['evaluation_id'] if stage == 'evaluation' else data['state'].experiment_id,
                                  name, stage, start=10 + index * 10, accepted=index != 7, ended=index != 7)
            seconds = (3, 63, 1801, 2403, 0, 4800, 97, 1)[index]
            start = events[1]['occurred_at']
            for event in events:
                event['observed_at'] = start + timedelta(seconds=seconds)
            if index != 7:
                events[-1]['occurred_at'] = start + timedelta(seconds=seconds)
            data['events'].extend(events)
        totals = experiment_totals(experiment_sections(data))
        self.assertEqual(totals, dict(elapsed='02:32:48', input_tokens=17928, output_tokens=4624))
        parsed = PanelParser(render_status(data))
        self.assertEqual(''.join(parsed.totals).strip(),
                         'Totals: Elapsed (02:32:48), tokens in (17,928), tokens out (4,624)')

    def test_totals_preserve_missing_metrics_and_measured_zero_usage(self):
        data = status_data()
        self.assertEqual(experiment_totals(experiment_sections(data)),
                         dict(elapsed='—', input_tokens=None, output_tokens=None))
        data['events'] = conversation('selection-cycle', 'training', 'selection')
        response = json.loads(data['events'][2]['content'])
        response['usage'] = dict(prompt_tokens=0)
        data['events'][2]['content'] = json.dumps(response)
        self.assertEqual(experiment_totals(experiment_sections(data)),
                         dict(elapsed='00:03', input_tokens=0, output_tokens=None))
        parsed = PanelParser(render_status(data))
        self.assertEqual(''.join(parsed.totals).strip(),
                         'Totals: Elapsed (00:03), tokens in (0), tokens out (—)')

    def test_prior_evaluation_hypothesis_survives_selection_and_simulation_phases(self):
        data = status_data()
        data['state'].proposals['reward-signals'] = ViewProposal('New hypothesis, not evaluated yet.', {})
        for phase in ('choosing', 'ready', 'submitting', 'running', 'comparing'):
            data['state'].phase = phase
            self.assertEqual(experiment_sections(data)[0]['hypothesis'], 'Previous tested hypothesis.')
        data['state'].phase = 'evaluating'
        data['evaluation_id'] = data['state'].experiment_id
        self.assertEqual(experiment_sections(data)[0]['hypothesis'], 'New hypothesis, not evaluated yet.')

    def test_active_elapsed_uses_database_clock_without_adding_the_utc_offset(self):
        data = status_data()
        data['events'] = conversation('evaluation-cycle', 'reward-signals', 'evaluation',
                                      accepted=False, ended=False)
        started = datetime(2026, 11, 26, 12, 0, 0)
        observed = started + timedelta(minutes=4, seconds=6)
        for event in data['events']:
            event['occurred_at'] = started
            event['observed_at'] = observed
        section = experiment_sections(data)[0]
        self.assertEqual(section['status'], 'In progress')
        self.assertEqual(section['elapsed'], '04:06')
        html = render_status(data)
        self.assertIn('04:06', html)
        self.assertNotIn('05:04:06', html)
        self.assertIn('<strong>Observations:</strong> In progress', html)

    def test_completed_elapsed_uses_the_recorded_end_time(self):
        data = status_data()
        data['events'] = conversation('evaluation-cycle', 'reward-signals', 'evaluation')
        for event in data['events']:
            event['observed_at'] += timedelta(hours=5)
        self.assertEqual(experiment_sections(data)[0]['elapsed'], '00:03')

    def test_shared_values_identify_the_view_that_saved_them(self):
        data = status_data()
        data['state'].proposals['training'] = ViewProposal('A shared proposal.', {
            'training.gamma': .95, 'training.sequence_length': 8, 'new seed': True,
        })
        before = deepcopy(data)
        sections = {s['id']: s for s in experiment_sections(data)}
        self.assertEqual(data, before)
        gamma = next(row for row in sections['selection-reward-signals']['rows'] if row['label'] == 'Gamma')
        self.assertEqual(gamma['baseline'], '0.96')
        self.assertEqual(gamma['choice'], '0.95')
        self.assertTrue(gamma['saved'])
        self.assertEqual(gamma['shared'], dict(id='selection-training', label='Training'))
        self.assertIn('href="#selection-training"', render_status(data))

    def test_pending_active_failed_and_retried_views_are_distinguished(self):
        data = status_data()
        self.assertTrue(all(section['status'] == 'Waiting' for section in experiment_sections(data)))
        self.assertEqual(render_status(data).count('<strong>Observations:</strong> Waiting'), 4)
        data['events'] = conversation('selection-cycle', 'training', 'selection', accepted=False, ended=False)
        section = next(s for s in experiment_sections(data) if s['id'] == 'selection-training')
        self.assertEqual(section['status'], 'In progress')
        self.assertTrue(section['open'])
        data['events'] = conversation('selection-cycle', 'training', 'selection', accepted=False,
                                      error='<script>Rejected values</script>')
        html = render_status(data)
        self.assertIn('Failed', html)
        self.assertIn('&lt;script&gt;Rejected values&lt;/script&gt;', html)
        self.assertNotIn('<script>Rejected', html)
        data['events'] += conversation('selection-cycle', 'training', 'selection', start=30)
        section = next(s for s in experiment_sections(data) if s['id'] == 'selection-training')
        self.assertEqual(section['status'], 'Saved')
        self.assertEqual(section['prompt_id'], 30)

    def test_uninitialized_and_synthetic_panels_do_not_invent_model_requests(self):
        empty = dict(state=None, events=[], selection_config=None, reference_config=None,
                     latest_config=None, evaluation_id=None)
        html = render_status(empty)
        self.assertEqual(len(PanelParser(html).panels), 8)
        self.assertEqual(html.count('Reasoning: —'), 4)
        self.assertEqual(html.count('Response (details): —'), 4)
        data = status_data()
        data['state'].synthetic = True
        data['state'].proposals = {'reward-signals': ViewProposal('Startup hypothesis.', {'game.rewards.food': 12})}
        section = next(s for s in experiment_sections(data) if s['id'] == 'selection-reward-signals')
        self.assertEqual(section['status'], 'Synthetic startup')
        self.assertIsNone(section['prompt_id'])
        self.assertIsNone(section['input_tokens'])
        self.assertFalse(section['saved'])
        self.assertIn('Configuration and hypotheses loaded from startup files.', render_status(data))

    def test_invalid_response_is_reported_as_failure_with_missing_usage(self):
        data = status_data()
        data['events'] = conversation('selection-cycle', 'training', 'selection', accepted=False, error='Invalid JSON')
        data['events'][2]['content'] = 'Invalid JSON response'
        section = next(s for s in experiment_sections(data) if s['id'] == 'selection-training')
        self.assertEqual(section['status'], 'Failed')
        self.assertIsNone(section['input_tokens'])
        self.assertIn('Invalid JSON', render_status(data))
        renderer = ReportRenderer()
        for content in ('<script>Invalid JSON response</script>', '[]', '{"error":"Rejected"}'):
            event = dict(event_id=99, category='Conversation', name='reply_received', content=content)
            html = renderer.event(event).decode()
            self.assertIn('Reply #99', html)
            self.assertNotIn('<script>Invalid', html)


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
                    if stage == 'evaluation' else 'Select parameters.'))
            self.log.log(row['name'], row['category'], row['log_level'], content,
                         process_id=process, parent_event_id=parent, parameter=name, source_name=name)

    def test_current_pass_and_preceding_evaluations_are_read_outside_recent_event_limit(self):
        first, second = self.ids
        config = SimulationConfiguration.defaults()
        state = ExperimentState(first, 'evaluating', deepcopy(config))
        ExperimentDb(self.db).save(state)
        self.record(first, 'architecture', 'evaluation')
        self.record(first, 'training', 'selection')  # Must not leak into the new selection pass.
        state = ExperimentState(second, 'choosing', deepcopy(config), order=list(VIEWS))
        ExperimentDb(self.db).save(state)
        self.record(second, 'reward-signals', 'selection')
        state.config['game']['rewards']['food'] = 12
        ExperimentDb(self.db).save(state)
        for _ in range(501):
            self.log.log('status_test', 'System', 'INFO', 'Unrelated event.', process_id=second)
        data = ExperimentStatusDb(self.db).read()
        self.assertEqual(data['state'], state)
        self.assertEqual(data['evaluation_id'], first)
        self.assertEqual(data['selection_config']['game']['rewards']['food'], 10)
        self.assertTrue(all('LARGE_IMAGE' not in (event['content'] or '') for event in data['events']))
        data.update(reference_config=config, latest_config=state.config)
        sections = {s['id']: s for s in experiment_sections(data)}
        self.assertEqual(sections['evaluation-architecture']['status'], 'Saved')
        self.assertEqual(sections['selection-reward-signals']['status'], 'Saved')
        self.assertEqual(sections['selection-training']['status'], 'Waiting')
        # A new evaluation pass starts pending instead of showing the preceding pass's saved views.
        state.phase = 'evaluating'
        ExperimentDb(self.db).save(state)
        data = ExperimentStatusDb(self.db).read()
        data.update(reference_config=config, latest_config=state.config)
        self.assertTrue(all(s['status'] == 'Waiting' for s in experiment_sections(data)[:4]))

    def test_active_elapsed_uses_mariadb_time_in_a_non_utc_session(self):
        self.db.execute("SET time_zone = '-05:00'")
        frozen = int(datetime(2026, 11, 26, 17, 4, 6, tzinfo=timezone.utc).timestamp())
        self.db.execute('SET timestamp = %s', (frozen,))
        process = self.ids[0]
        config = SimulationConfiguration.defaults()
        ExperimentDb(self.db).save(ExperimentState(process, 'evaluating', config))
        parent = self.log.log('conversation_started', 'Conversation', 'INFO', 'Evaluating.', process_id=process)
        self.log.log('prompt_sent', 'Conversation', 'INFO', json.dumps(dict(role='user', content=[
            dict(type='text', text='Evaluate results.')])), process_id=process,
            parent_event_id=parent, parameter='reward-signals', source_name='reward-signals')
        request = self.log.log('llm_request_started', 'LLM', 'INFO', 'Evaluating.', process_id=process,
                               parent_event_id=parent, parameter='reward-signals', source_name='reward-signals')
        self.db.execute('''UPDATE events SET occurred_at = CURRENT_TIMESTAMP(6) - INTERVAL 246 SECOND
                           WHERE event_id = %s''', (request,))
        data = ExperimentStatusDb(self.db).read()
        data.update(reference_config=config, latest_config=config)
        section = experiment_sections(data)[0]
        self.assertEqual(section['status'], 'In progress')
        self.assertEqual(section['elapsed'], '04:06')
