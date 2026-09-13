import json
import unittest
from unittest.mock import Mock, patch

from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb
from ax3l.app.snakelab.prompts.ComparisonEpsilonPair import ComparisonEpsilonPair


class EpsilonComparisonTests(unittest.TestCase):
    def test_sorted_grid_preserves_repeats_zero_and_missing_pairs(self):
        db = Mock()
        db.query.return_value = [
            {"initial": initial, "decay": decay,
             "status": status, "high_score": score}
            for initial, decay, status, score in [
                (.96, .99, "completed", 39),
                (.91, .95, "completed", 36),
                (.91, .95, "completed", 0),
                (.91, .95, "completed", 34),
                (.91, .95, "completed", 34),
                (.96, .95, "failed", 100),
                (.96, .97, "running", 90),
                (.91, .97, "completed", None),
            ]
        ]
        self.assertEqual(SnakeLabDb(db).get_epsilon_report("gold"), [
            {"initial": .91, "pairs": [
                {"decay": .95, "scores": [0, 34, 34, 36]},
                {"decay": .97, "scores": []},
                {"decay": .99, "scores": []},
            ]},
            {"initial": .96, "pairs": [
                {"decay": .95, "scores": []},
                {"decay": .97, "scores": []},
                {"decay": .99, "scores": [39]},
            ]},
        ])
        sql, args = db.query.call_args.args
        self.assertNotIn("c.seed = g.seed", sql)
        self.assertNotIn("c.epsilon_initial = g.epsilon_initial", sql)
        self.assertNotIn("c.epsilon_decay = g.epsilon_decay", sql)
        self.assertIn("c.epochs = g.epochs", sql)
        self.assertEqual(args, ("gold",))

    def test_empty_report(self):
        db = Mock()
        db.query.return_value = []
        self.assertEqual(SnakeLabDb(db).get_epsilon_report("gold"), [])

    def test_prompt_displays_golden_and_report_and_refreshes(self):
        with patch("ax3l.app.snakelab.prompts.ComparisonEpsilonPair.SnakeLab") as snake:
            snake.return_value.get_run_result.return_value = {
                "config": {"epsilon": {"initial": .96, "decay": .97}},
                "high_score": 37,
            }
            rows = [{"initial": .91, "pairs": [{"decay": .95, "scores": [34, 36]}]}]
            snake.return_value.get_epsilon_report.return_value = rows
            prompt = ComparisonEpsilonPair("gold")
            content = prompt.to_md()
            self.assertIn("Current golden epsilon:\ninitial=0.96, decay=0.97, high_score=37.", content)
            report_json = content.split("```json\n")[1].split("```")[0]
            self.assertEqual(json.loads(report_json), rows)
            self.assertIn("across seeds", content)
            snake.return_value.get_epsilon_report.assert_called_once_with("gold")
            snake.return_value.get_epsilon_report.return_value = []
            prompt.refresh()
            self.assertIn("```json\n[]\n```", prompt.to_md())


if __name__ == "__main__":
    unittest.main()
