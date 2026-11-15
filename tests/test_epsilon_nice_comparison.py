"""Compare Nice pairs without mixing other architectures or exploration schedules."""

import json
import unittest
from unittest.mock import Mock, patch

from ax3l.app.snakelab.GenerateDefaultConfig import GenerateDefaultConfig
from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb
from ax3l.app.snakelab.prompts.ComparisonEpsilonNicePair import ComparisonEpsilonNicePair
from ax3l.app.snakelab.prompts.FirstContactEpsilonNicePair import FirstContactEpsilonNicePair
from ax3l.interface.SnakeLab import SnakeLab


class EpsilonNiceComparisonTests(unittest.TestCase):
    def test_completed_scores_are_sorted_and_other_settings_match(self):
        db = Mock()
        db.query.return_value = [dict(probability=p, steps=n, status=s, high_score=score)
            for p, n, s, score in ((.01, 20, 'completed', 5), (.005, 40, 'completed', 0),
                                   (.01, 20, 'completed', 3), (.005, 20, 'failed', 99))]
        self.assertEqual(SnakeLabDb(db).get_epsilon_nice_report('gold'), [
            {'probability': .005, 'pairs': [{'steps': 20, 'scores': []}, {'steps': 40, 'scores': [0]}]},
            {'probability': .01, 'pairs': [{'steps': 20, 'scores': [3, 5]}, {'steps': 40, 'scores': []}]},
        ])
        sql, parameters = db.query.call_args.args
        for column in ('model_type', 'model_heads', 'epsilon_initial', 'epsilon_decay'):
            self.assertIn(f'c.{column} = g.{column}', sql)
        for column in ('epsilon_nice_probability', 'epsilon_nice_steps', 'seed'):
            self.assertNotIn(f'c.{column} = g.{column}', sql)
        self.assertEqual(parameters, ('gold',))

    def test_prompts_explain_the_golden_schedule_and_joint_tuning(self):
        config = GenerateDefaultConfig().run()
        with patch('ax3l.app.snakelab.prompts.ComparisonEpsilonNicePair.SnakeLab') as snake:
            snake.return_value.get_run_result.return_value = dict(config=config, high_score=4)
            snake.return_value.get_epsilon_nice_report.return_value = []
            prompt = ComparisonEpsilonNicePair('gold')
            report = json.loads(prompt.to_md().split('```json\n')[1].split('```')[0])
            self.assertEqual(report['epsilon'], config['epsilon'])
            self.assertEqual(report['gold'], dict(probability=.005, steps=20, high_score=4))
        instructions = FirstContactEpsilonNicePair().to_md()
        for text in ('probability', 'steps', 'positive', '500-episode', 'next move'):
            self.assertIn(text, instructions)
        self.assertIn('value_1 = start chance: number; above 0; at most 0.1.', instructions)
        self.assertIn('value_2 = moves per detour: whole number; at least 1; at most 50.', instructions)

    def test_interface_closes_connection_on_success_and_failure(self):
        run = 'f6e72cb3-9bcf-4669-b368-a17c656bad79'
        for method in ('get_epsilon_nice_report', 'get_episode_diagnostics'):
            with patch('ax3l.interface.SnakeLab.DbMgr') as factory, patch('ax3l.interface.SnakeLab.SnakeLabDb') as dal:
                getattr(dal.return_value, method).return_value = []
                self.assertEqual(getattr(SnakeLab(), method)(run), [])
                factory.return_value.close.assert_called_once()
                getattr(dal.return_value, method).side_effect = RuntimeError('read failed')
                with self.assertRaises(RuntimeError):
                    getattr(SnakeLab(), method)(run)
                self.assertEqual(factory.return_value.close.call_count, 2)
