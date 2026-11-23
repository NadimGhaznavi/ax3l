import unittest
from unittest.mock import Mock

from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb


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


if __name__ == "__main__":
    unittest.main()
