"""Complete JSON snapshots stay read-only and tied to saved references."""

from copy import deepcopy
import json
import re
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from ax3l.activity.RunAnalysis import measure
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
from ax3l.entities.SimulationAnalysis import SimulationAnalysis
from ax3l.interface.SimulationConfiguration import SimulationConfiguration
from ax3l.interface.SimulationData import SimulationData


class SimulationDataTests(unittest.TestCase):
    def setUp(self):
        self.gold, self.latest, self.best = [str(uuid4()) for _ in range(3)]
        self.store = self.enterContext(patch('ax3l.interface.SimulationData.ExperimentDb')).return_value
        self.config = SimulationConfiguration.defaults()
        self.draft = ConfigurationDraft(str(uuid4()), self.gold,
            dict(latest=self.latest, golden=self.gold, all_time_best=self.best), deepcopy(self.config))
        self.store.draft.return_value = self.draft
        metrics = measure([dict(score=0, steps=20, outcome='max_moves', loss=None,
                               epsilon_injections=2, epsilon_nice_injections=3)], 2)
        self.analyses = {run_id: SimulationAnalysis(run_id, deepcopy(self.config), deepcopy(metrics),
            'Score trends: Scores stayed low.\nScore distribution: High scores were rare.\nTraining loss: Loss declined.')
            for run_id in (self.gold, self.latest, self.best)}
        self.analyses[self.best].config['seed'] += 1
        self.store.analysis.side_effect = self.analyses.get
        self.data = SimulationData(Mock())

    def read(self, url):
        return self.data.read({'draft_id': self.draft.draft_id, 'url': url})

    def payload(self, url):
        page = self.read(url)['page']
        if url in ('/draft', '/latest', '/golden', '/best'):
            page = page.split('```json\n', 1)[1].split('\n```', 1)[0]
        return json.loads(page)

    def test_navigation_reaches_complete_snapshots_without_section_requests(self):
        pending, pages = ['/'], {}
        configs = dict(draft=self.draft.config, latest=self.analyses[self.latest].config,
                       golden=self.analyses[self.gold].config, best=self.analyses[self.best].config)
        while pending:
            url = pending.pop()
            if url in pages:
                continue
            result = self.read(url)
            self.assertEqual(result['status'], 'ok', url)
            page = pages[url] = result['page']
            self.assertNotRegex(page, r'(?m)^\s*\|')
            for run_id in (*self.analyses, self.draft.draft_id):
                self.assertNotIn(run_id.split('-')[0], page)
            if url != '/':
                data = json.loads(page.split('```json\n', 1)[1].split('\n```', 1)[0])
                scope = url[1:]
                self.assertEqual(data['scope'], scope)
                self.assertEqual(data['seed'], configs[scope]['seed'])
                self.assertEqual(data['config'], configs[scope])
                if scope != 'draft':
                    run_id = self.draft.references['all_time_best' if scope == 'best' else scope]
                    self.assertEqual(data['metrics'], self.analyses[run_id].metrics)
                    self.assertEqual(data['summary'], self.analyses[run_id].summary)
            pending.extend(re.findall(r'\]\(([^)]+)\)', page))
        self.assertEqual(set(pages), {'/', '/draft', '/latest', '/golden', '/best'})
        self.assertIs(self.payload('/best')['same_seed_as_draft'], False)
        self.store.save_draft.assert_not_called()
        self.store.save_analysis.assert_not_called()

    def test_lookup_loads_only_the_requested_reference_and_uses_frozen_ids(self):
        self.read('/')
        self.read('/draft')
        self.store.analysis.assert_not_called()
        self.read('/latest/model')
        self.store.analysis.assert_called_once_with(self.latest)
        self.store.draft.assert_called_with(self.draft.draft_id)
        self.assertEqual(self.payload('/latest')['score_difference'], 0)
        self.assertEqual([call.args[0] for call in self.store.analysis.call_args_list],
                         [self.latest, self.latest, self.gold])

    def test_draft_reads_include_saved_earlier_choices_after_restart(self):
        self.draft.config['model']['hidden_size'] = 104
        self.draft.selections = ['hidden_size']
        self.draft.phase, self.draft.parameter = 'choosing', 'gamma'
        snapshot = self.payload('/draft')
        self.assertEqual(snapshot['config'], self.draft.config)
        self.assertEqual(snapshot['saved_settings'], ['hidden_size'])
        self.assertEqual(snapshot['current_setting'], 'gamma')
        self.assertEqual(snapshot['phase'], 'choosing')
        self.assertEqual(self.payload('/draft/model')['model']['hidden_size'], 104)
        self.assertEqual(self.payload('/golden/model')['model']['hidden_size'], 64)

    def test_shared_reference_runs_have_one_index_entry_and_all_aliases_work(self):
        self.draft.references = dict.fromkeys(self.draft.references, self.gold)
        index = self.read('/')['page']
        self.assertEqual(re.findall(r'\]\(([^)]+)\)', index), ['/latest', '/draft'])
        self.assertEqual(len(re.findall(r'\]\(', index)), 2)
        for label in ('latest', 'golden', 'best'):
            page = self.read(f'/{label}')['page']
            self.assertEqual(self.payload(f'/{label}')['roles'], ['latest', 'golden', 'best'])
            self.assertIs(self.payload(f'/{label}')['same_seed_as_draft'], True)
            self.assertEqual(re.findall(r'\]\(([^)]+)\)', page), ['/'])

    def test_bad_paths_and_arguments_are_rejected_before_reading_data(self):
        for url in ('/../golden', '/latest/../../draft', 'https://example.com', '/best?x=1',
                    '/golden/', '/all_time_best', f'/{self.gold}', '/draft/scores'):
            self.assertEqual(self.read(url)['status'], 'rejected', url)
        for payload in ({}, [], {'draft_id': self.draft.draft_id, 'url': 5},
                        {'draft_id': self.draft.draft_id, 'url': '/', 'run_id': self.gold}):
            self.assertEqual(self.data.read(payload)['status'], 'rejected')
        self.store.draft.assert_not_called()
        self.store.analysis.assert_not_called()

    def test_missing_draft_rejects_but_unfinished_reference_is_a_workflow_error(self):
        self.store.draft.return_value = None
        self.assertEqual(self.read('/')['status'], 'rejected')
        self.store.draft.return_value = self.draft
        self.store.analysis.side_effect = None
        self.store.analysis.return_value = None
        with self.assertRaisesRegex(RuntimeError, 'must finish'):
            self.read('/golden/scores')

    def test_missing_score_statistics_remain_unrecorded(self):
        self.analyses[self.latest].metrics.update(measure([], 0))
        scores = self.payload('/latest/scores')
        self.assertIsNone(scores['mean_score'])
        self.assertIsNone(scores['mean_first_50_scores'])
        self.assertEqual(scores['high_score'], 0)
        self.assertEqual(scores['episodes'], 0)
        self.assertEqual(self.payload('/latest')['metrics'], self.analyses[self.latest].metrics)

    def test_complete_run_snapshot_preserves_unrecorded_observations(self):
        for summary in (None, ''):
            analysis = self.analyses[self.latest]
            self.analyses[self.latest] = SimulationAnalysis(analysis.run_id, analysis.config, analysis.metrics, summary)
            snapshot = self.payload('/latest')
            self.assertEqual(snapshot['summary'], summary)
            self.assertEqual(snapshot['config'], analysis.config)
            self.assertEqual(snapshot['metrics'], analysis.metrics)

    def test_json_preserves_numbers_percentages_and_observation_text(self):
        metrics = self.analyses[self.latest].metrics
        metrics['mean_score'] = 1 / 3
        metrics['termination_reasons']['wall']['percent'] = 100 / 3
        self.assertEqual(self.payload('/latest/scores')['mean_score'], 1 / 3)
        self.assertEqual(self.payload('/latest/endings')['termination_reasons'], metrics['termination_reasons'])
        for page, key in (('model', 'model'), ('training', 'training'), ('exploration', 'epsilon_nice')):
            self.assertEqual(self.payload(f'/latest/{page}')[key], self.config[key])
        self.assertEqual(self.payload('/latest/rewards')['rewards'], self.config['game']['rewards'])
        self.assertEqual(self.payload('/latest/activity')['total_steps'], metrics['total_steps'])
        self.analyses[self.latest] = SimulationAnalysis(self.latest, self.config, metrics,
            'Score trends: "flat".\nTraining loss: missing — path \\loss.')
        self.assertEqual(self.payload('/latest/notes')['summary'], self.analyses[self.latest].summary)
        snapshot = self.payload('/latest')
        self.assertEqual(snapshot['metrics'], metrics)
        self.assertEqual(snapshot['summary'], self.analyses[self.latest].summary)
        self.assertIs(self.payload('/best')['same_seed_as_draft'], False)


class AnalysisRunDataTests(unittest.TestCase):
    def setUp(self):
        self.store = self.enterContext(patch('ax3l.interface.SimulationData.ExperimentDb')).return_value
        self.snake = self.enterContext(patch('ax3l.interface.SimulationData.SnakeLab')).return_value
        self.run_id = str(uuid4())
        self.config = SimulationConfiguration.defaults()
        self.config['training']['learning_rate'] = .003
        self.config['epsilon_nice']['steps'] = 40
        self.snake.get_run_result.return_value = dict(status='completed', config=self.config)
        self.data = SimulationData(Mock())

    def read(self, url):
        return self.data.read_run(dict(run_id=self.run_id, url=url))

    def test_chart_settings_are_original_run_values_without_waiting_for_saved_analysis(self):
        original = deepcopy(self.config)
        pending, pages = ['/run'], {}
        while pending:
            url = pending.pop()
            if url in pages:
                continue
            result = self.read(url)
            self.assertEqual(result['status'], 'ok', url)
            page = pages[url] = result['page']
            self.assertNotIn(self.run_id, page)
            self.assertLessEqual(len(page.split()), 220, url)
            pending.extend(re.findall(r'\]\(([^)]+)\)', page))
        self.assertEqual(len(pages), 8)
        self.assertEqual(json.loads(pages['/run/config'])['config'], original)
        self.assertEqual(json.loads(pages['/run/training'])['training']['learning_rate'], .003)
        self.assertEqual(json.loads(pages['/run/exploration'])['epsilon_nice']['steps'], 40)
        self.assertEqual(self.read('/')['page'], pages['/run'])
        for call in self.snake.get_run_result.call_args_list:
            self.assertEqual(call.args, (self.run_id,))
        self.store.analysis.assert_not_called()
        self.store.draft.assert_not_called()
        self.store.save_draft.assert_not_called()
        self.store.save_analysis.assert_not_called()
        self.assertEqual(self.config, original)

    def test_recommendation_rules_use_current_schema_limits_and_only_tunable_fields(self):
        data = json.loads(self.read('/run/rules')['page'])
        parameters = data['parameters']
        self.assertEqual(parameters['training.learning_rate']['maximum'], .005)
        self.assertEqual(parameters['epsilon_nice.probability']['maximum'], .1)
        self.assertEqual(parameters['epsilon_nice.steps']['maximum'], 40)
        self.assertEqual(parameters['model.hidden_size']['minimum'], 32)
        self.assertEqual(parameters['model.hidden_size']['maximum'], 128)
        self.assertEqual(parameters['model.hidden_size']['multipleOf'], 8)
        self.assertEqual(parameters['model.layers']['enum'], [1, 2, 3])
        self.assertEqual(parameters['model.dropout']['enum'], [n / 100 for n in range(11)])
        self.assertEqual(parameters['game.rewards.empty'], dict(type='number', minimum=-2, maximum=2))
        for field in ('snake', 'wall'):
            self.assertEqual(parameters[f'game.rewards.{field}'], dict(type='number', minimum=-20, maximum=0))
        self.assertEqual(parameters['game.rewards.food'], dict(type='number', minimum=0, maximum=20))
        self.assertNotIn('game.rewards.max_moves', parameters)
        self.assertNotIn('seed', parameters)
        self.assertNotIn('epochs', parameters)
        self.assertNotIn('model.heads', parameters)
        self.assertEqual(data['reward_pair_rule'], 'closer_to_food + further_from_food <= 0')

    def test_invalid_bindings_and_paths_are_rejected_before_run_lookup(self):
        for url in ('/draft', '/latest/training', '/run/notes', '/run/../config',
                    '/run/config?run_id=other', 'https://example.com'):
            with self.subTest(url=url):
                self.assertEqual(self.read(url)['status'], 'rejected')
        for payload in (None, {}, dict(run_id='bad-id', url='/run'), dict(run_id=True, url='/run'),
                        dict(run_id=self.run_id, url=1),
                        dict(run_id=self.run_id, draft_id='other', url='/run/config')):
            with self.subTest(payload=payload):
                self.assertEqual(self.data.read_run(payload)['status'], 'rejected')
        self.snake.get_run_result.assert_not_called()

    def test_missing_or_unfinished_run_is_a_workflow_error(self):
        for result in (None, dict(status='running'), dict(status='failed')):
            self.snake.get_run_result.return_value = result
            with self.subTest(result=result), self.assertRaisesRegex(RuntimeError, 'completed simulation'):
                self.read('/run/config')
