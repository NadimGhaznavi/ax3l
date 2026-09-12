import json
import unittest
from unittest.mock import Mock, patch

from ax3l.app.DynamicPrompt import DynamicPrompt
from ax3l.app.snakelab.prompts.GoldenConfig import GoldenConfig


class GoldenConfigTests(unittest.TestCase):
    def test_refresh_reloads_current_selection_and_configuration(self):
        with patch("ax3l.app.snakelab.prompts.GoldenConfig.EventLogDb") as events, patch(
            "ax3l.app.snakelab.prompts.GoldenConfig.SnakeLab"
        ) as snake:
            events.return_value.current_golden_config.side_effect = [
                {"process_id": "first-run", "reason": "Seeded database with default config."},
                {"process_id": "next-run", "reason": "Parameter x: 2 > 4"},
            ]
            configs = [{"training": {"learning_rate": 0.0021}},
                       {"training": {"learning_rate": 0.003}, "seed": 1970}]
            snake.return_value.get_config.side_effect = configs
            prompt = GoldenConfig(Mock())
            self.assertIsInstance(prompt, DynamicPrompt)
            self.assertIn("Seeded database with default config.", prompt.to_md())
            self.assertEqual(json.loads(prompt.to_md().split("```json\n")[1].split("\n```")[0]), configs[0])
            prompt.refresh()
            snake.return_value.get_config.assert_called_with("next-run")
            self.assertIn("Parameter x: 2 > 4", prompt.to_md())
            self.assertNotIn("Seeded database", prompt.to_md())
            self.assertEqual(json.loads(prompt.to_md().split("```json\n")[1].split("\n```")[0]), configs[1])
            self.assertEqual(json.loads(prompt.to_json()), {"role": "user", "content": prompt.to_md()})

    def test_missing_selection_or_run_fails(self):
        with patch("ax3l.app.snakelab.prompts.GoldenConfig.EventLogDb") as events, patch(
            "ax3l.app.snakelab.prompts.GoldenConfig.SnakeLab"
        ) as snake:
            events.return_value.current_golden_config.return_value = None
            with self.assertRaisesRegex(ValueError, "No golden configuration"):
                GoldenConfig(Mock())
            snake.return_value.get_config.assert_not_called()
            events.return_value.current_golden_config.return_value = {"process_id": "missing-run", "reason": "seed"}
            snake.return_value.get_config.return_value = None
            with self.assertRaisesRegex(ValueError, "missing-run was not found"):
                GoldenConfig(Mock())
