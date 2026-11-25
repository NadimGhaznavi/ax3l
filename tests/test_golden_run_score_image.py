"""Verify score windows and the PNG guides the vision model reads."""

from base64 import b64decode
from copy import deepcopy
from io import BytesIO
import unittest

from PIL import Image

from ax3l.activity.ScorePercentiles import score_percentiles
from ax3l.presentation.GoldenRunScoreImage import golden_run_score_image


class ScorePercentilesTests(unittest.TestCase):
    def test_interpolates_per_window_in_epoch_order_and_keeps_partial_window(self):
        episodes = [dict(episode=i + 1, score=i) for i in reversed(range(21))]
        original = deepcopy(episodes)
        points = score_percentiles(episodes, window_size=10)
        self.assertEqual([point['epoch'] for point in points], [10, 20, 21])
        for point, expected in zip(points, ((8.1, 2.25), (18.1, 12.25), (20, 20))):
            self.assertAlmostEqual(point['p90'], expected[0])
            self.assertAlmostEqual(point['p25'], expected[1])
        self.assertEqual(episodes, original)

    def test_default_windows_cover_50_epochs_with_a_final_partial_window(self):
        points = score_percentiles([dict(episode=i, score=0) for i in range(1, 122)])
        self.assertEqual(points, [dict(epoch=epoch, p90=0, p25=0) for epoch in (50, 100, 121)])
        self.assertEqual(score_percentiles([]), [])


class GoldenRunScoreImageTests(unittest.TestCase):
    def test_png_has_at_least_five_interior_horizontal_guides_in_each_panel(self):
        for scores in ([], [0], [1, 2, 3], [20] * 100, list(range(150)), [0, 10000]):
            with self.subTest(scores=scores[:3]):
                episodes = [dict(episode=i, score=score) for i, score in enumerate(scores, 1)]
                url = golden_run_score_image(episodes)
                self.assertTrue(url.startswith('data:image/png;base64,'))
                with Image.open(BytesIO(b64decode(url.split(',')[1]))) as image:
                    self.assertEqual(image.format, 'PNG')
                    self.assertEqual(image.size, (1056, 768))
                    for top, bottom in ((150, 366), (454, 670)):
                        guides = [y for y in range(top + 1, bottom)
                                  if image.getpixel((128, y)) == (53, 73, 94)]
                        self.assertGreaterEqual(len(guides), 5)

    def test_both_percentile_curves_are_drawn(self):
        url = golden_run_score_image([dict(episode=i, score=i % 20) for i in range(1, 151)])
        with Image.open(BytesIO(b64decode(url.split(',')[1]))) as image:
            pixels = {color for _, color in image.getcolors(image.width * image.height)}
            self.assertIn((77, 179, 255), pixels)
            self.assertIn((255, 189, 112), pixels)
