"""Qwen can select any setting at startup, after duplicates, or after a unique change."""

from copy import deepcopy
from dataclasses import asdict
import json
import unittest
from unittest.mock import Mock, patch

from ax3l.app.snakelab.SelectParameterHandler import SelectParameterHandler
from ax3l.app.snakelab.SubmitPairValuesHandler import SubmitPairValuesHandler
from ax3l.app.snakelab.SubmitSingleValueHandler import SubmitSingleValueHandler
from ax3l.entities.ConfigurationDraft import ConfigurationDraft, PARAMETER_ORDER
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


class SelectParameterHandlerTests(unittest.TestCase):
    def setUp(self):
        shared = 'ax3l.app.snakelab.SubmitSingleValueHandler.'
        self.snake = self.enterContext(patch(shared + 'SnakeLab')).return_value
        self.experiments = self.enterContext(patch(shared + 'ExperimentDb')).return_value
        self.enterContext(patch('ax3l.app.snakelab.SelectParameterHandler.ExperimentDb',
                                return_value=self.experiments))
        self.db = Mock()
        self.handler = SelectParameterHandler(self.db)
        self.bind()

    def bind(self):
        self.draft = ConfigurationDraft('draft', 'gold', {'golden': 'gold'}, SimulationConfiguration.defaults(),
                                        PARAMETER_ORDER.copy(), 'selecting_parameter')
        self.experiments.draft.return_value = self.draft

    def select(self, parameter='hidden_size', draft_id='draft'):
        return self.handler.submit(dict(draft_id=draft_id, parameter=parameter))

    def test_every_single_and_pair_can_be_reopened_without_changing_values(self):
        for parameter in PARAMETER_ORDER:
            with self.subTest(parameter=parameter):
                self.bind()
                original = deepcopy(self.draft)
                self.experiments.save_draft.reset_mock()
                self.assertEqual(self.select(parameter), dict(status='ok', draft_id='draft', phase='choosing'))
                self.assertEqual(self.draft.next_parameter, parameter)
                self.assertEqual(self.draft.selections, [name for name in PARAMETER_ORDER if name != parameter])
                self.assertEqual(self.draft.config, original.config)
                self.assertEqual(self.draft.references, original.references)
                self.experiments.save_draft.assert_called_once_with(self.draft)
        self.snake.is_config_unique.assert_not_called()
        self.snake.submit_simulation.assert_not_called()

    def test_invalid_names_and_arguments_do_not_read_or_change_the_draft(self):
        for parameter in ('seed', 'epochs', 'revision', 'probability', 'unknown', None, [], True):
            with self.subTest(parameter=parameter):
                self.assertEqual(self.select(parameter)['status'], 'rejected')
        for payload in (None, {}, dict(draft_id='draft'),
                        dict(draft_id='draft', parameter='layers', value=2),
                        dict(draft_id=None, parameter='layers')):
            self.assertEqual(self.handler.submit(payload)['status'], 'rejected')
        self.experiments.draft.assert_not_called()
        self.experiments.save_draft.assert_not_called()

    def test_stale_drafts_and_choices_outside_the_revision_phase_are_rejected(self):
        original = deepcopy(self.draft)
        self.assertEqual(self.select(draft_id='old')['status'], 'rejected')
        self.assertEqual(self.draft, original)
        for phase in ('choosing', 'preparing', 'ready', 'submitting', 'submitted', 'completed'):
            self.draft.phase = phase
            self.assertEqual(self.select()['status'], 'rejected')
        self.experiments.draft.return_value = None
        self.assertEqual(self.select()['status'], 'rejected')
        self.experiments.save_draft.assert_not_called()

    def test_repeated_duplicates_return_to_parameter_selection_after_each_revision(self):
        self.snake.is_config_unique.side_effect = [False, False, True]
        single = SubmitSingleValueHandler(self.db)
        pair = SubmitPairValuesHandler(self.db)
        self.select('hidden_size')
        result = single.submit(dict(draft_id='draft', parameter='hidden_size', value=96))
        self.assertEqual(result['phase'], 'selecting_parameter')
        self.select('layers')
        result = single.submit(dict(draft_id='draft', parameter='layers', value=3))
        self.assertEqual(result['phase'], 'selecting_parameter')
        self.select('epsilon_pair')
        result = pair.submit(dict(draft_id='draft', pair='epsilon_pair', value_1=.91, value_2=.95))
        self.assertEqual(result['phase'], 'reviewing')
        self.assertEqual(self.draft.config['model']['hidden_size'], 96)
        self.assertEqual(self.draft.config['model']['layers'], 3)
        self.assertEqual(self.draft.config['epsilon']['initial'], .91)
        self.assertEqual(self.draft.config['epsilon_nice'], dict(probability=.05, steps=20))
        self.assertEqual(set(self.draft.selections), set(PARAMETER_ORDER))
        self.assertEqual(len(self.draft.selections), len(PARAMETER_ORDER))
        self.assertEqual(self.snake.is_config_unique.call_count, 3)
        self.snake.submit_simulation.assert_not_called()

    def test_revision_phase_and_reopened_choice_survive_snapshot_round_trips(self):
        restored = ConfigurationDraft(**json.loads(json.dumps(asdict(self.draft))))
        self.assertEqual(restored.phase, 'selecting_parameter')
        self.assertIsNone(restored.next_parameter)
        self.select('learning_rate')
        restored = ConfigurationDraft(**json.loads(json.dumps(asdict(self.draft))))
        self.assertEqual(restored.next_parameter, 'learning_rate')
        self.assertEqual(restored.config, self.draft.config)

    def test_persistence_errors_propagate(self):
        self.experiments.save_draft.side_effect = RuntimeError('write failed')
        with self.assertRaisesRegex(RuntimeError, 'write failed'):
            self.select()

    def test_baseline_can_select_any_parameter_without_previous_choices(self):
        self.draft.selections = []
        self.assertEqual(self.select('gamma')['phase'], 'choosing')
        self.assertEqual(self.draft.next_parameter, 'gamma')
        self.assertEqual(self.draft.selections, [])

    def test_unique_candidate_can_revisit_the_same_parameter_repeatedly(self):
        self.snake.is_config_unique.return_value = True
        self.draft.selections = []
        single = SubmitSingleValueHandler(self.db)
        for value in (2, 3, 1):
            self.select('layers')
            self.assertEqual(single.submit(dict(draft_id='draft', parameter='layers', value=value))['phase'],
                             'reviewing')
            self.assertEqual(self.draft.selections, ['layers'])
        self.assertEqual(self.draft.config['model']['layers'], 1)
