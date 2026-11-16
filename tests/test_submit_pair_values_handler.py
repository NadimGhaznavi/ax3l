"""Joint choices are atomic; duplicates stay in the selected pair's conversation."""

from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

from ax3l.app.snakelab.SubmitPairValuesHandler import SubmitPairValuesHandler
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


class SubmitPairValuesHandlerTests(unittest.TestCase):
    def setUp(self):
        module = 'ax3l.app.snakelab.SubmitSingleValueHandler.'
        self.snake = self.enterContext(patch(module + 'SnakeLab')).return_value
        self.snake.is_config_unique.return_value = True
        self.experiments = self.enterContext(patch(module + 'ExperimentDb')).return_value
        self.handler = SubmitPairValuesHandler(Mock())
        self.bind('epsilon_pair')

    def bind(self, pair):
        self.draft = ConfigurationDraft('draft', 'gold', {'golden': 'gold'}, SimulationConfiguration.defaults(),
                                        phase='choosing', parameter=pair)
        self.experiments.draft.return_value = self.draft

    def submit(self, pair='epsilon_pair', first=.91, second=.95):
        return self.handler.submit({'draft_id': 'draft', 'pair': pair, 'value_1': first, 'value_2': second})

    def test_invalid_pairs_and_values_never_write_a_partial_choice(self):
        for pair, first, second in (('unknown', 1, 1), ('epsilon_pair', .91, 1.5),
                                    ('epsilon_pair', True, .95), ('epsilon_pair', '.91', .95),
                                    ('reward_pair', 6, 0), ('reward_pair', .25, -.1),
                                    ('reward_pair', 2.5, -3), ('epsilon_nice_pair', 0, 20),
                                    ('epsilon_nice_pair', .01, 2.5)):
            with self.subTest(pair=pair, values=(first, second)):
                self.assertEqual(self.submit(pair, first, second)['code'], 'invalid_value')
        for payload in (None, {}, {'pair': 'epsilon_pair', 'value_1': .91}):
            self.assertEqual(self.handler.submit(payload)['code'], 'invalid_value')
        self.experiments.draft.assert_not_called()
        self.experiments.save_draft.assert_not_called()
        self.snake.submit_simulation.assert_not_called()

    def test_both_values_are_saved_together_and_unchanged_values_are_allowed(self):
        for pair, first, second, section, expected in (
            ('epsilon_pair', .96, .97, 'epsilon', {'initial': .96, 'decay': .97, 'minimum': 0}),
            ('reward_pair', .25, -.5, 'game', None),
            ('epsilon_nice_pair', .01, 40, 'epsilon_nice', {'probability': .01, 'steps': 40}),
        ):
            with self.subTest(pair=pair):
                self.bind(pair)
                result = self.submit(pair, first, second)
                self.assertEqual(result['status'], 'ok')
                if expected is not None:
                    self.assertEqual(self.draft.config[section], expected)
                else:
                    self.assertEqual(self.draft.config['game']['rewards']['closer_to_food'], .25)
                    self.assertEqual(self.draft.config['game']['rewards']['further_from_food'], -.5)
        self.assertEqual(self.draft.phase, 'reviewing')
        self.assertIsNone(self.draft.next_parameter)
        self.assertEqual(self.snake.is_config_unique.call_count, 3)
        self.snake.is_config_unique.assert_called_with(self.draft.config)
        self.snake.submit_simulation.assert_not_called()

    def test_duplicate_configuration_rejects_the_whole_pair_without_leaving_its_choice(self):
        self.bind('epsilon_nice_pair')
        original = deepcopy(self.draft)
        self.snake.is_config_unique.return_value = False
        result = self.submit('epsilon_nice_pair', .005, 20)
        self.assertEqual(result['code'], 'duplicate_configuration')
        self.assertIn('submit_pair_values', result['prompt']['content'])
        self.assertEqual(self.draft, original)
        self.assertEqual(self.draft.next_parameter, 'epsilon_nice_pair')
        self.experiments.save_draft.assert_not_called()
        self.snake.is_config_unique.return_value = True
        self.assertEqual(self.submit('epsilon_nice_pair', .01, 40)['phase'], 'reviewing')
        self.experiments.save_draft.assert_called_once_with(self.draft)
        self.snake.submit_simulation.assert_not_called()

    def test_epsilon_nice_caps_reject_the_whole_pair_and_accept_both_upper_bounds(self):
        self.bind('epsilon_nice_pair')
        original = deepcopy(self.draft)
        for probability, steps, label in ((.01, 51, 'moves per detour'),
                                           (.11, 20, 'start chance'), (.1, 1000, 'moves per detour')):
            with self.subTest(probability=probability, steps=steps):
                result = self.submit('epsilon_nice_pair', probability, steps)
                self.assertEqual(result['code'], 'invalid_value')
                self.assertIn(label, result['reason'])
                self.assertEqual(self.draft, original)
        self.experiments.draft.assert_not_called()
        self.experiments.save_draft.assert_not_called()
        self.snake.is_config_unique.assert_not_called()
        self.snake.submit_simulation.assert_not_called()
        self.assertEqual(self.submit('epsilon_nice_pair', .1, 40)['status'], 'ok')
        self.assertEqual(self.draft.config['epsilon_nice'], dict(probability=.1, steps=40))
        self.assertEqual(self.draft.phase, 'reviewing')
        self.experiments.save_draft.assert_called_once_with(self.draft)
