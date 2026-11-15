"""Bound data browsing stays small, readable, read-only, and tied to saved references."""

from copy import deepcopy
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

    def test_navigation_reaches_all_facts_as_small_english_pages_without_ids(self):
        pending, pages = ['/'], {}
        while pending:
            url = pending.pop()
            if url in pages:
                continue
            result = self.read(url)
            self.assertEqual(result['status'], 'ok', url)
            page = pages[url] = result['page']
            self.assertLessEqual(len(page.split()), 160, url)
            self.assertNotIn('{', page)
            for run_id in (*self.analyses, self.draft.draft_id):
                self.assertNotIn(run_id.split('-')[0], page)
            pending.extend(re.findall(r'\]\(([^)]+)\)', page))
        self.assertEqual(len(pages), 37)
        self.assertIn('high score: 2', pages['/latest/scores'])
        self.assertIn('move limit: 1 (100.0%)', pages['/latest/endings'])
        self.assertIn('safe detour moves: 3', pages['/latest/activity'])
        self.assertIn('Loss declined.', pages['/latest/notes'])
        self.assertIn('replay frames: 100000', pages['/golden/training'])
        self.assertIn('Different seed: historical context', pages['/best'])
        self.assertIn('Episodes: 500', pages['/draft/game'])
        self.assertIn('Safe detours: chance 0.005; moves 20', pages['/draft/exploration'])
        self.store.save_draft.assert_not_called()
        self.store.save_analysis.assert_not_called()

    def test_lookup_loads_only_the_requested_reference_and_uses_frozen_ids(self):
        self.read('/')
        self.read('/draft')
        self.store.analysis.assert_not_called()
        self.read('/latest/model')
        self.store.analysis.assert_called_once_with(self.latest)
        self.store.draft.assert_called_with(self.draft.draft_id)
        self.assertIn('gap: 0', self.read('/latest')['page'])
        self.assertEqual([call.args[0] for call in self.store.analysis.call_args_list],
                         [self.latest, self.latest, self.gold])

    def test_draft_reads_include_saved_earlier_choices_after_restart(self):
        self.draft.config['model']['hidden_size'] = 272
        self.draft.selections = ['hidden_size']
        page = self.read('/draft')['page']
        self.assertIn('hidden size: 272 (chosen)', page)
        self.assertIn('sequence length: 8 (pending)', page)
        self.assertIn('hidden size: 272', self.read('/draft/model')['page'])
        self.assertIn('hidden size: 224', self.read('/golden/model')['page'])

    def test_shared_reference_runs_have_one_index_entry_and_all_aliases_work(self):
        self.draft.references = dict.fromkeys(self.draft.references, self.gold)
        index = self.read('/')['page']
        self.assertIn('[latest, golden, best](/latest)', index)
        self.assertEqual(len(re.findall(r'\]\(', index)), 2)
        for label in ('latest', 'golden', 'best'):
            page = self.read(f'/{label}')['page']
            self.assertIn('Roles: latest, golden, best', page)
            self.assertIn('Same seed as draft.', page)

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
        page = self.read('/latest/scores')['page']
        self.assertIn('mean score: unrecorded', page)
        self.assertIn('first 50 mean: unrecorded', page)
