import json
import unittest
from unittest.mock import Mock, patch

from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb
from ax3l.app.snakelab.prompts.ComparisonRewardPair import ComparisonRewardPair
from ax3l.interface.SnakeLab import SnakeLab


class RewardComparisonTests(unittest.TestCase):
    def test_complete_sorted_grid_and_scored_completed_runs_only(self):
        db = Mock()
        db.query.return_value = [
            {"closer_to_food": json.dumps(first), "further_from_food": json.dumps(second),
             "status": status, "high_score": score}
            for first, second, status, score in [
                (3, -3, "completed", 39), (3, -3, "completed", 41),
                (3.0, -3.0, "completed", 37), (3, -3, "completed", 37),
                (0, -6, "completed", 0), (6, 0, "completed", 12),
                (2, -2, "failed", 99), (2, -2, "running", 99),
                (2, -2, "completed", None),
                (7, -2, "completed", 99), (2, -7, "completed", 99),
                (2.5, -2, "completed", 99),
            ]
        ]
        report = SnakeLabDb(db).get_reward_report("gold")
        self.assertEqual(list(report), ["0", "1", "2", "3", "4", "5", "6"])
        for pairs in report.values():
            self.assertEqual(list(pairs), ["-6", "-5", "-4", "-3", "-2", "-1", "0"])
        self.assertEqual(report["3"]["-3"], [37, 37, 39, 41])
        self.assertEqual(report["0"]["-6"], [0])
        self.assertEqual(report["6"]["0"], [12])
        self.assertEqual(sum(bool(scores) for pairs in report.values() for scores in pairs.values()), 3)
        sql, args = db.query.call_args.args
        for alias in ("r", "g"):
            self.assertIn(
                f"JSON_REMOVE({alias}.config, '$.seed', '$.game.rewards.closer_to_food', '$.game.rewards.further_from_food')",
                sql,
            )
        self.assertEqual(args, ("gold",))

    def test_no_runs_still_produces_49_independent_empty_cells(self):
        db = Mock()
        db.query.return_value = []
        report = SnakeLabDb(db).get_reward_report("gold")
        cells = [scores for pairs in report.values() for scores in pairs.values()]
        self.assertEqual(len(cells), 49)
        self.assertTrue(all(scores == [] for scores in cells))
        self.assertEqual(len({id(scores) for scores in cells}), 49)

    def test_prompt_json_contains_gold_and_grid_and_refreshes(self):
        with patch("ax3l.app.snakelab.prompts.ComparisonRewardPair.SnakeLab") as snake:
            baseline = {"config": {"game": {"rewards": {
                "closer_to_food": 2, "further_from_food": -2}}}, "high_score": 37}
            snake.return_value.get_run_result.return_value = baseline
            grid = {"0": {"-6": []}, "3": {"-3": [37, 39, 41]}}
            snake.return_value.get_reward_report.return_value = grid
            prompt = ComparisonRewardPair("gold")
            report = json.loads(prompt.to_md().split("```json\n")[1].split("```")[0])
            self.assertEqual(report, {"gold": {"closer_to_food": 2,
                                             "further_from_food": -2, "high_score": 37},
                                      "results": grid})
            self.assertIn("across all seeds", prompt.to_md())
            snake.return_value.get_reward_report.assert_called_once_with("gold")
            baseline["high_score"] = 40
            prompt.refresh()
            self.assertIn('"high_score": 40', prompt.to_md())

    def test_interface_closes_database_on_success_and_failure(self):
        golden_id = "f6e72cb3-9bcf-4669-b368-a17c656bad79"
        with patch("ax3l.interface.SnakeLab.DbMgr") as db, patch("ax3l.interface.SnakeLab.SnakeLabDb") as reports:
            reports.return_value.get_reward_report.return_value = {"0": {"-6": []}}
            self.assertEqual(SnakeLab().get_reward_report(golden_id), {"0": {"-6": []}})
            reports.return_value.get_reward_report.assert_called_once_with(golden_id)
            db.return_value.close.assert_called_once()
            db.return_value.reset_mock()
            reports.return_value.get_reward_report.side_effect = RuntimeError("database failure")
            with self.assertRaises(RuntimeError):
                SnakeLab().get_reward_report(golden_id)
            db.return_value.close.assert_called_once()
