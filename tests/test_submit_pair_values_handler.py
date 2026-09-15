from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

from jsonschema import ValidationError

from ax3l.constants.DAx3l import DAx3l
from ax3l.app.snakelab.GenerateDefaultConfig import GenerateDefaultConfig
from ax3l.app.snakelab.SubmitPairValuesHandler import SubmitPairValuesHandler


class SubmitPairValuesHandlerTests(unittest.TestCase):
    def setUp(self):
        self.db = Mock()
        shared = 'ax3l.app.snakelab.SubmitSingleValueHandler'
        self.snake = self.enterContext(patch(shared + '.SnakeLab')).return_value
        self.events = self.enterContext(patch(shared + '.EventLogDb')).return_value
        self.events.current_golden_config.return_value = {'process_id': 'golden-run'}
        self.baseline = GenerateDefaultConfig().run()
        self.snake.get_config.return_value = self.baseline
        self.snake.is_config_unique.return_value = True
        self.snake.submit_simulation.return_value = 'new-run'
        self.handler = SubmitPairValuesHandler(self.db)

    def test_invalid_pairs_and_values_do_not_reach_backend(self):
        valid = {'pair': 'epsilon_pair', 'value_1': .91, 'value_2': .95}
        proposals = [None, {}, {**valid, 'extra': 1}, {'pair': 'epsilon_pair', 'value_1': .91}]
        proposals += [{**valid, 'pair': pair} for pair in (None, [], 'seed', 'learning_rate', 'unknown')]
        for field in ('value_1', 'value_2'):
            proposals += [{**valid, field: value} for value in (True, '0.95', None, float('nan'), float('inf'), -.1, 1)]
        proposals += [
            {'pair': 'reward_pair', 'value_1': first, 'value_2': second}
            for first, second in ((-1, -2), (7, -2), (2, -7), (2, 1), (2.5, -2), (2, -2.5))
        ]
        for proposal in proposals:
            with self.subTest(proposal=proposal):
                result = self.handler.submit(proposal)
                self.assertEqual(result['code'], 'invalid_value')
                self.assertEqual(result['prompt']['role'], 'user')
        self.events.current_golden_config.assert_not_called()
        self.snake.submit_simulation.assert_not_called()

    def test_joint_changes_preserve_baseline_and_log_one_submission(self):
        for pair, section, values in (
            ('epsilon_pair', ('epsilon',), {'initial': .85, 'decay': .999}),
            ('reward_pair', ('game', 'rewards'), {'closer_to_food': 6.0, 'further_from_food': -6.0}),
        ):
            with self.subTest(pair=pair):
                self.db.reset_mock()
                self.snake.reset_mock()
                original = deepcopy(self.baseline)
                expected = deepcopy(original)
                node = expected
                for key in section:
                    node = node[key]
                node.update(values)
                first, second = values.values()
                result = self.handler.submit({'pair': pair, 'value_1': first, 'value_2': second})
                self.assertEqual(result, {'status': 'ok', 'run_id': 'new-run'})
                self.assertEqual(self.db.log.call_args.kwargs['ax3l_version'], DAx3l.VERSION)
                self.snake.is_config_unique.assert_called_once_with(expected)
                self.snake.submit_simulation.assert_called_once_with(expected)
                self.assertEqual(self.baseline, original)
                self.assertEqual([c.args[0] for c in self.db.log.call_args_list],
                                 ['proposal_accepted', 'simulation_submitted'])
                self.assertIn(pair, self.db.log.call_args_list[0].args[3])
                if pair == 'reward_pair':
                    rewards = self.snake.submit_simulation.call_args.args[0]['game']['rewards']
                    self.assertIs(type(rewards['closer_to_food']), int)
                    self.assertIs(type(rewards['further_from_food']), int)

    def test_unchanged_and_historical_pairs_are_duplicates(self):
        epsilon = self.baseline['epsilon']
        payload = {'pair': 'epsilon_pair', 'value_1': epsilon['initial'], 'value_2': epsilon['decay']}
        self.assertEqual(self.handler.submit(payload)['code'], 'duplicate_config')
        self.snake.is_config_unique.assert_not_called()
        self.snake.is_config_unique.return_value = False
        payload['value_1'] = .91
        self.assertEqual(self.handler.submit(payload)['code'], 'duplicate_config')
        self.snake.submit_simulation.assert_not_called()

    def test_one_value_may_remain_unchanged(self):
        self.assertEqual(self.handler.submit({
            'pair': 'epsilon_pair', 'value_1': .91,
            'value_2': self.baseline['epsilon']['decay'],
        })['status'], 'ok')

    def test_missing_or_broken_golden_is_a_server_error(self):
        payload = {'pair': 'reward_pair', 'value_1': 3, 'value_2': -3}
        self.events.current_golden_config.return_value = None
        with self.assertRaises(RuntimeError):
            self.handler.submit(payload)
        self.events.current_golden_config.return_value = {'process_id': 'golden-run'}
        self.snake.get_config.return_value = None
        with self.assertRaises(RuntimeError):
            self.handler.submit(payload)
        self.snake.get_config.return_value = self.baseline
        self.baseline['epochs'] = -1
        with self.assertRaises(ValidationError):
            self.handler.submit(payload)
        self.snake.submit_simulation.assert_not_called()
        self.db.log.assert_not_called()

    def test_submission_failure_propagates_without_retry_or_acceptance(self):
        self.snake.submit_simulation.side_effect = TimeoutError('timeout')
        with self.assertRaises(TimeoutError):
            self.handler.submit({'pair': 'reward_pair', 'value_1': 3, 'value_2': -3})
        self.snake.submit_simulation.assert_called_once()
        self.db.log.assert_not_called()
