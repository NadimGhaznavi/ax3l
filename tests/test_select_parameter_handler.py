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
        self.draft = ConfigurationDraft('draft', 'gold', {'golden': 'gold'}, SimulationConfiguration.defaults())
        self.experiments.draft.return_value = self.draft

    def select(self, parameter='hidden_size', draft_id='draft'):
        return self.handler.submit(dict(draft_id=draft_id, parameter=parameter))

    def test_every_unused_single_and_pair_can_be_selected_without_changing_values(self):
        for parameter in PARAMETER_ORDER:
            with self.subTest(parameter=parameter):
                self.bind()
                self.draft.selections = [name for name in PARAMETER_ORDER if name != parameter]
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

    def test_repeated_duplicates_keep_the_same_parameter_until_a_unique_value(self):
        self.snake.is_config_unique.side_effect = [False, False, True]
        self.draft.selections = []
        single = SubmitSingleValueHandler(self.db)
        self.select('hidden_size')
        original = deepcopy(self.draft)
        self.experiments.save_draft.reset_mock()
        for value in (96, 104):
            result = single.submit(dict(draft_id='draft', parameter='hidden_size', value=value))
            self.assertEqual(result['code'], 'duplicate_configuration')
            self.assertEqual(self.draft, original)
            self.assertEqual(self.select('layers')['status'], 'rejected')
            self.experiments.save_draft.assert_not_called()
        result = single.submit(dict(draft_id='draft', parameter='hidden_size', value=112))
        self.assertEqual(result['phase'], 'reviewing')
        self.assertEqual(self.draft.config['model']['hidden_size'], 112)
        self.assertEqual(self.draft.config['model']['layers'], 1)
        self.assertEqual(self.draft.config['epsilon_nice'], dict(probability=.05, steps=20))
        self.assertEqual(self.draft.selections, ['hidden_size'])
        self.experiments.save_draft.assert_called_once_with(self.draft)
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

    def test_used_single_and_pair_cannot_be_selected_again_after_a_snapshot_round_trip(self):
        self.snake.is_config_unique.return_value = True
        for parameter, handler, payload in (
            ('learning_rate', SubmitSingleValueHandler, dict(parameter='learning_rate', value=.002)),
            ('epsilon_pair', SubmitPairValuesHandler, dict(pair='epsilon_pair', value_1=.91, value_2=.95)),
        ):
            with self.subTest(parameter=parameter):
                self.bind()
                self.select(parameter)
                self.assertEqual(handler(self.db).submit(dict(draft_id='draft', **payload))['phase'], 'reviewing')
                self.draft = ConfigurationDraft(**json.loads(json.dumps(asdict(self.draft))))
                self.experiments.draft.return_value = self.draft
                original = deepcopy(self.draft)
                self.experiments.save_draft.reset_mock()
                result = self.select(parameter)
                self.assertEqual(result['status'], 'rejected')
                self.assertIn('already been chosen', result['reason'])
                self.assertEqual(self.draft, original)
                self.experiments.save_draft.assert_not_called()
