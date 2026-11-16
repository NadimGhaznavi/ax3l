"""Single choices update a durable draft without starting simulations."""

from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

from ax3l.app.snakelab.SubmitSingleValueHandler import SubmitSingleValueHandler
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


class SubmitSingleValueHandlerTests(unittest.TestCase):
    def setUp(self):
        module = 'ax3l.app.snakelab.SubmitSingleValueHandler.'
        self.snake = self.enterContext(patch(module + 'SnakeLab')).return_value
        self.snake.is_config_unique.return_value = True
        self.experiments = self.enterContext(patch(module + 'ExperimentDb')).return_value
        self.handler = SubmitSingleValueHandler(Mock())
        self.baseline = SimulationConfiguration.defaults()
        self.bind('learning_rate')

    def bind(self, parameter):
        self.draft = ConfigurationDraft('draft', 'gold', {'golden': 'gold'}, deepcopy(self.baseline),
                                        phase='choosing', parameter=parameter)
        self.experiments.draft.return_value = self.draft

    def submit(self, parameter='learning_rate', value=.003, **extra):
        return self.handler.submit({'draft_id': 'draft', 'parameter': parameter, 'value': value, **extra})

    def test_invalid_values_do_not_read_or_write_the_draft(self):
        for value in (True, '0.003', None, float('nan'), float('inf'), 0, .02):
            with self.subTest(value=value):
                self.assertEqual(self.submit(value=value)['code'], 'invalid_value')
        for parameter, value in (('seed', 1), ('epochs', 500), ('initial', .95), ('unknown', 1),
                                 ('batch_size', 25), ('hidden_size', 24), ('hidden_size', 136),
                                 ('hidden_size', 33), ('layers', 0), ('layers', 4), ('layers', 1.5),
                                 ('dropout', -.01), ('dropout', .11), ('dropout', .005)):
            self.assertEqual(self.submit(parameter, value)['code'], 'invalid_value')
        self.assertEqual(self.submit(extra=1)['code'], 'invalid_value')
        self.assertEqual(self.handler.submit({})['code'], 'invalid_value')
        self.experiments.draft.assert_not_called()
        self.experiments.save_draft.assert_not_called()
        self.snake.submit_simulation.assert_not_called()

    def test_choice_preserves_other_values_and_checks_uniqueness_without_submitting(self):
        self.draft.config['model']['hidden_size'] = 96
        original = deepcopy(self.baseline)
        result = self.submit()
        self.assertEqual(result, {'status': 'ok', 'draft_id': 'draft', 'phase': 'reviewing'})
        saved = self.experiments.save_draft.call_args.args[0]
        self.assertEqual(saved.config['model']['hidden_size'], 96)
        self.assertEqual(saved.config['training']['learning_rate'], .003)
        self.assertIsNone(saved.next_parameter)
        self.assertEqual(saved.selections, ['learning_rate'])
        self.assertEqual(self.baseline, original)
        self.snake.is_config_unique.assert_called_once_with(saved.config)
        self.snake.submit_simulation.assert_not_called()

    def test_unchanged_values_are_rejected_even_when_the_complete_draft_is_unique(self):
        for parameter, value in (('learning_rate', .001), ('layers', 1.0), ('dropout', .05)):
            with self.subTest(parameter=parameter):
                self.bind(parameter)
                self.draft.config['model']['hidden_size'] = 96
                original = deepcopy(self.draft)
                result = self.submit(parameter, value)
                self.assertEqual(result['status'], 'rejected')
                self.assertIn('current values', result['reason'])
                self.assertEqual(self.draft, original)
        self.experiments.save_draft.assert_not_called()
        self.snake.is_config_unique.assert_not_called()

    def test_all_single_parameters_are_staged(self):
        for name, value in (('hidden_size', 32), ('layers', 3), ('dropout', .02),
                             ('sequence_length', 12), ('batch_size', 26),
                             ('learning_rate', .003), ('gamma', .97)):
            with self.subTest(parameter=name):
                self.bind(name)
                self.assertEqual(self.submit(name, value)['status'], 'ok')
                self.assertEqual(self.draft.selections[-1], name)
        self.snake.submit_simulation.assert_not_called()

    def test_stale_draft_and_wrong_parameter_cannot_change_the_active_draft(self):
        self.assertEqual(self.submit('gamma', .97)['status'], 'rejected')
        self.assertEqual(self.handler.submit({'draft_id': 'old', 'parameter': 'learning_rate',
                                              'value': .003})['status'], 'rejected')
        self.experiments.save_draft.assert_not_called()

    def test_persistence_failure_propagates(self):
        self.experiments.save_draft.side_effect = RuntimeError('write failed')
        with self.assertRaisesRegex(RuntimeError, 'write failed'):
            self.submit()
        self.experiments.save_draft.assert_called_once()
        self.snake.submit_simulation.assert_not_called()

    def test_uniqueness_failure_does_not_mutate_or_save_the_draft(self):
        original = deepcopy(self.draft)
        self.snake.is_config_unique.side_effect = RuntimeError('database unavailable')
        with self.assertRaisesRegex(RuntimeError, 'database unavailable'):
            self.submit()
        self.assertEqual(self.draft, original)
        self.experiments.save_draft.assert_not_called()
