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
from ax3l.presentation.reporting.ExperimentStatus import experiment_sections
from ax3l.presentation.reporting.ReportRenderer import ReportRenderer


def conversation(process, name, stage, start=10, accepted=True, error=None, ended=True):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = []
    def event(category, name, content, **fields):
        row = dict(event_id=start + len(rows), occurred_at=now + timedelta(seconds=len(rows)),
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
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'details' and attrs.get('class') == 'view-section':
            self.panels.append(attrs)
        if tag == 'a':
            self.links.append(attrs['href'])


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
        for heading in ('Saved', 'Setting or step', 'LLM details', 'Baseline', 'LLM choice',
                        'Elapsed', 'Input tokens', 'Output tokens'):
            self.assertEqual(html.count(f'>{heading}</th>'), 8)
        self.assertIn('Food Reward', html)
        self.assertIn('Reward for eating food.', html)
        self.assertEqual(html.count('2,241'), 2)
        self.assertIn('viewStatus.replaceChildren', html)
        self.assertIn('section.open = saved.open', html)

    def test_prior_evaluation_hypothesis_survives_selection_and_simulation_phases(self):
        data = status_data()
        data['state'].proposals['reward-signals'] = ViewProposal('New hypothesis, not evaluated yet.', {})
        for phase in ('choosing', 'ready', 'submitting', 'running', 'comparing'):
            data['state'].phase = phase
            self.assertEqual(experiment_sections(data)[0]['hypothesis'], 'Previous tested hypothesis.')
        data['state'].phase = 'evaluating'
        data['evaluation_id'] = data['state'].experiment_id
        self.assertEqual(experiment_sections(data)[0]['hypothesis'], 'New hypothesis, not evaluated yet.')

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
        self.assertEqual(len(PanelParser(render_status(empty)).panels), 8)
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
