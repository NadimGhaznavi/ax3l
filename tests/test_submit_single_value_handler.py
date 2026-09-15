from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

from ax3l.constants.DAx3l import DAx3l
from ax3l.app.snakelab.GenerateDefaultConfig import GenerateDefaultConfig
from ax3l.app.snakelab.SubmitSingleValueHandler import SubmitSingleValueHandler


class SubmitSingleValueHandlerTests(unittest.TestCase):
    def setUp(self):
        self.db = Mock()
        self.snake = self.enterContext(patch('ax3l.app.snakelab.SubmitSingleValueHandler.SnakeLab')).return_value
        self.events = self.enterContext(patch('ax3l.app.snakelab.SubmitSingleValueHandler.EventLogDb')).return_value
        self.events.current_golden_config.return_value = {'process_id': 'golden-run'}
        self.baseline = GenerateDefaultConfig().run()
        self.snake.get_config.return_value = self.baseline
        self.snake.is_config_unique.return_value = True
        self.snake.submit_simulation.return_value = 'new-run'
        self.handler = SubmitSingleValueHandler(self.db)

    def test_illegal_values_return_invalid_value_prompt_without_submission(self):
        proposals = [{}, {'parameter': 'learning_rate', 'value': 0.003, 'extra': 1}]
        proposals += [{'parameter': 'learning_rate', 'value': value}
                      for value in (True, '0.003', None, float('nan'), float('inf'), 0, 0.02)]
        proposals += [{'parameter': 'unknown', 'value': 1},
                      {'parameter': 'epochs', 'value': 501},
                      {'parameter': 'batch_size', 'value': 25}]
        for proposal in proposals:
            with self.subTest(proposal=proposal):
                result = self.handler.submit(proposal)
                self.assertEqual(result['code'], 'invalid_value')
                self.assertEqual(result['source_name'], 'InvalidValue')
                self.assertIn('Invalid value:', result['prompt']['content'])
        self.snake.submit_simulation.assert_not_called()
        self.events.current_golden_config.assert_not_called()

    def test_unchanged_and_historical_configurations_are_duplicates(self):
        rate = self.baseline['training']['learning_rate']
        result = self.handler.submit({'parameter': 'learning_rate', 'value': rate})
        self.assertEqual(result['code'], 'duplicate_config')
        self.assertEqual(result['source_name'], 'NoDupes')
        self.snake.is_config_unique.assert_not_called()
        self.snake.is_config_unique.return_value = False
        result = self.handler.submit({'parameter': 'learning_rate', 'value': 0.003})
        self.assertEqual(result['code'], 'duplicate_config')
        self.assertIn('already exists in the simulation database', result['prompt']['content'])
        self.snake.submit_simulation.assert_not_called()

    def test_only_selected_field_changes_and_submission_is_logged_once(self):
        original = deepcopy(self.baseline)
        result = self.handler.submit({'parameter': 'learning_rate', 'value': 0.003})
        candidate = deepcopy(original)
        candidate['training']['learning_rate'] = 0.003
        self.assertEqual(result, {'status': 'ok', 'run_id': 'new-run'})
        self.snake.is_config_unique.assert_called_once_with(candidate)
        self.snake.submit_simulation.assert_called_once_with(candidate)
        self.assertEqual(self.db.log.call_args.kwargs["ax3l_version"], DAx3l.VERSION)
        self.assertEqual(self.baseline, original)
        self.assertEqual([c.args[0] for c in self.db.log.call_args_list],
                         ['proposal_accepted', 'simulation_submitted'])

    def test_all_single_parameters_change_exactly_one_field(self):
        for section, parameter, value in [('model', 'hidden_size', 240),
                                           ('training', 'sequence_length', 12),
                                           ('training', 'batch_size', 26),
                                           ('training', 'learning_rate', .003),
                                           ('training', 'gamma', .97)]:
            with self.subTest(parameter=parameter):
                candidate = deepcopy(self.baseline)
                candidate[section][parameter] = value
                self.assertEqual(self.handler.submit({'parameter': parameter, 'value': value})['status'], 'ok')
                self.snake.submit_simulation.assert_called_with(candidate)

    def test_pairs_and_managed_settings_are_rejected_even_with_legal_values(self):
        for parameter, value in [('closer_to_food', 3), ('further_from_food', -3),
                                 ('initial', .95), ('decay', .98), ('seed', 1971),
                                 ('epochs', 1500), ('layers', 4)]:
            with self.subTest(parameter=parameter):
                self.assertEqual(self.handler.submit({'parameter': parameter, 'value': value})['code'],
                                 'invalid_value')
        self.snake.submit_simulation.assert_not_called()
        self.events.current_golden_config.assert_not_called()

    def test_backend_failure_is_not_retried_or_logged_as_accepted(self):
        self.snake.submit_simulation.side_effect = TimeoutError('timeout')
        with self.assertRaises(TimeoutError):
            self.handler.submit({'parameter': 'learning_rate', 'value': 0.003})
        self.snake.submit_simulation.assert_called_once()
        self.db.log.assert_not_called()
