import base64
import json
import unittest
from unittest.mock import patch

from ax3l.app.snakelab.prompts.LossPlot import LossPlot


RUN_ID = "f6e72cb3-9bcf-4669-b368-a17c656bad79"


class LossPlotTests(unittest.TestCase):
    def test_refresh_and_image_message_preserve_episodes_and_gaps(self):
        with patch("ax3l.app.snakelab.prompts.LossPlot.SnakeLab") as snake, patch(
            "plotly.graph_objects.Figure.to_image", autospec=True,
            side_effect=[b"first PNG", b"second PNG"],
        ) as render:
            snake.return_value.get_episode_losses.side_effect = [
                [(1, None), (2, 0.8), (3, None), (4, 0.0)], [(1, 0.5), (2, 0.25)],
            ]
            prompt = LossPlot(RUN_ID)
            figure = render.call_args.args[0]
            self.assertEqual(list(figure.data[0].x), [1, 2, 3, 4])
            self.assertEqual(list(figure.data[0].y), [None, 0.8, None, 0.0])
            self.assertFalse(figure.data[0].connectgaps)
            self.assertEqual(figure.layout.xaxis.title.text, "Episode")
            self.assertEqual(render.call_args.kwargs, {"format": "png", "scale": 1})
            message = json.loads(prompt.to_json())
            self.assertEqual(message["role"], "user")
            self.assertEqual(message["content"][0]["type"], "text")
            self.assertIn(RUN_ID, message["content"][0]["text"])
            image = message["content"][1]
            self.assertEqual(image["type"], "image_url")
            self.assertEqual(base64.b64decode(image["image_url"]["url"].split(",", 1)[1]), b"first PNG")
            self.assertIn(image["image_url"]["url"], prompt.to_md())
            prompt.refresh()
            snake.return_value.get_episode_losses.assert_called_with(RUN_ID)
            image = json.loads(prompt.to_json())["content"][1]
            self.assertEqual(base64.b64decode(image["image_url"]["url"].split(",", 1)[1]), b"second PNG")

    def test_no_loss_does_not_render_a_misleading_chart(self):
        with patch("ax3l.app.snakelab.prompts.LossPlot.SnakeLab") as snake, patch(
            "plotly.graph_objects.Figure.to_image"
        ) as render:
            for losses in ([], [(1, None), (2, None)]):
                snake.return_value.get_episode_losses.return_value = losses
                with self.assertRaisesRegex(ValueError, "No training losses"):
                    LossPlot(RUN_ID)
            render.assert_not_called()
