import unittest
from unittest.mock import Mock

from ax3l.app.snakelab.SingleParameters import SINGLE_PARAMETERS
from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb
from ax3l.app.snakelab.prompts.FirstContactSingle import FirstContactSingle
from ax3l.app.snakelab.prompts.ComparisonSingle import ComparisonSingle


class SingleParameterTests(unittest.TestCase):
    def test_prompts_offer_only_tunable_single_parameters_with_schema_rules(self):
        expected = {'hidden_size', 'sequence_length', 'batch_size', 'learning_rate', 'gamma'}
        self.assertEqual(set(SINGLE_PARAMETERS), expected)
        for parameter in expected:
            for prompt in (FirstContactSingle(parameter), ComparisonSingle(parameter)):
                content = prompt.to_md()
                self.assertIn(parameter, content)
                self.assertIn(SINGLE_PARAMETERS[parameter][1]['description'], content)
                for other in expected - {parameter}:
                    self.assertNotIn(other, content)
                self.assertIn('{"value": number}', content)

    def test_reports_use_parameter_path_and_preserve_seed_history(self):
        for name, (path, _) in SINGLE_PARAMETERS.items():
            with self.subTest(parameter=name):
                db = Mock()
                db.query.return_value = [
                    {name: '16', 'run_id': 'old', 'status': 'completed', 'high_score': 7, 'current_seed': 0},
                    {name: '16', 'run_id': 'failed', 'status': 'failed', 'high_score': 99, 'current_seed': 0},
                    {name: '16', 'run_id': 'gold', 'status': 'completed', 'high_score': 5, 'current_seed': 1},
                ]
                self.assertEqual(SnakeLabDb(db).get_parameter_report('gold', name), [
                    {name: 16, 'results': [{'run_id': 'gold', 'status': 'completed', 'high_score': 5}],
                     'history': [7]}])
                sql, args = db.query.call_args.args
                self.assertIn(f"JSON_REMOVE(r.config, '$.seed', '$.{'.'.join(path)}')", sql)
                self.assertIn(f"JSON_REMOVE(g.config, '$.seed', '$.{'.'.join(path)}')", sql)
                self.assertEqual(args, ('gold',))
        with self.assertRaises(KeyError):
            SnakeLabDb(Mock()).get_parameter_report('gold', 'initial')
