"""Verify score windows and the PNG guides the vision model reads."""

from base64 import b64decode
from copy import deepcopy
from io import BytesIO
import unittest

from PIL import Image

from ax3l.activity.ExplorationProgress import exploration_progress
from ax3l.activity.ScorePercentiles import score_percentiles
from ax3l.entities.ExperimentView import VIEWS
from ax3l.presentation.RunComparisonImage import run_comparison_image


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


class ExplorationProgressTests(unittest.TestCase):
    def test_uses_recorded_checkpoint_epsilon_and_move_weighted_override_rate(self):
        episodes = [dict(episode=3, epsilon=0, steps=0, epsilon_nice_injections=0),
                    dict(episode=2, epsilon=0, steps=90, epsilon_nice_injections=9),
                    dict(episode=1, epsilon=.7, steps=10, epsilon_nice_injections=0)]
        original = deepcopy(episodes)
        self.assertEqual(exploration_progress(episodes, window_size=2), [
            dict(epoch=2, epsilon=0, epsilon_nice_rate=.09, post_epsilon=True),
            dict(epoch=3, epsilon=0, epsilon_nice_rate=None, post_epsilon=True),
        ])
        self.assertEqual(episodes, original)
        self.assertEqual(exploration_progress([]), [])

    def test_default_150_epoch_windows_retain_partial_window_and_post_epsilon_transition(self):
        episodes = [dict(episode=i, epsilon=.4 if i <= 150 else 0, steps=10,
                         epsilon_nice_injections=0 if i <= 150 else 2) for i in range(1, 322)]
        self.assertEqual(exploration_progress(episodes), [
            dict(epoch=150, epsilon=.4, epsilon_nice_rate=0, post_epsilon=False),
            dict(epoch=300, epsilon=0, epsilon_nice_rate=.2, post_epsilon=True),
            dict(epoch=321, epsilon=0, epsilon_nice_rate=.2, post_epsilon=True),
        ])


class RunComparisonImageTests(unittest.TestCase):
    def test_png_has_at_least_five_interior_horizontal_guides_in_each_panel(self):
        for scores in ([], [0], [1, 2, 3], [20] * 100, list(range(150)), [0, 10000]):
            with self.subTest(scores=scores[:3]):
                episodes = [dict(episode=i, score=score) for i, score in enumerate(scores, 1)]
                url = run_comparison_image(VIEWS['architecture'], [], episodes)
                self.assertTrue(url.startswith('data:image/png;base64,'))
                with Image.open(BytesIO(b64decode(url.split(',')[1]))) as image:
                    self.assertEqual(image.format, 'PNG')
                    self.assertEqual(image.size, (1056, 768))
                    for top, bottom in ((178, 378), (452, 652)):
                        guides = [y for y in range(top + 1, bottom)
                                  if image.getpixel((128, y)) == (53, 73, 94)]
                        self.assertGreaterEqual(len(guides), 5)

    def test_both_runs_appear_in_each_score_panel_on_shared_axes_without_extending_shorter_run(self):
        golden = [dict(episode=i, score=10) for i in range(1, 101)]
        latest = [dict(episode=i, score=20) for i in range(1, 151)]
        url = run_comparison_image(VIEWS['architecture'], golden, latest)
        with Image.open(BytesIO(b64decode(url.split(',')[1]))) as image:
            for top, bottom in ((178, 378), (452, 652)):
                pixels = {color for _, color in image.crop((118, top, 1008, bottom + 4)).getcolors(200000)}
                self.assertIn((77, 179, 255), pixels)
                self.assertIn((255, 189, 112), pixels)
                # The shared score ceiling is 20; golden ends at epoch 100, score 10.
                self.assertEqual(image.getpixel((709, (top + bottom) // 2)), (255, 189, 112))
                self.assertNotEqual(image.getpixel((900, (top + bottom) // 2)), (255, 189, 112))
                self.assertEqual(image.getpixel((1004, top)), (77, 179, 255))

    def test_exploration_panel_shows_sampled_epsilon_and_dashed_observed_overrides(self):
        episodes = [dict(episode=i, score=i % 20, epsilon=.8 if i <= 150 else 0,
                         steps=10, epsilon_nice_injections=2 if i > 150 else 0)
                    for i in range(1, 601)]
        url = run_comparison_image(VIEWS['exploration'], [], episodes)
        with Image.open(BytesIO(b64decode(url.split(',')[1]))) as image:
            self.assertEqual(image.size, (1056, 1000))
            # Epsilon .8 at epoch 150, then zero at 300, where the solid line ends.
            self.assertEqual(image.getpixel((339, 212)), (77, 179, 255))
            self.assertEqual(image.getpixel((561, 348)), (77, 179, 255))
            self.assertNotEqual(image.getpixel((900, 348)), (77, 179, 255))
            # Observed overrides stay at 20%, using dashed segments after expiry.
            self.assertEqual(image.getpixel((1004, 314)), (77, 179, 255))
            pixels = [image.getpixel((x, 314)) for x in range(600, 900)]
            self.assertIn((77, 179, 255), pixels)
            self.assertTrue(any(color != (77, 179, 255) for color in pixels))

    def test_empty_exploration_and_zero_move_windows_still_produce_readable_pngs(self):
        for episodes in ([], [dict(episode=1, score=0, epsilon=0, steps=0, epsilon_nice_injections=0)]):
            with self.subTest(episodes=episodes):
                url = run_comparison_image(VIEWS['exploration'], [], episodes)
                with Image.open(BytesIO(b64decode(url.split(',')[1]))) as image:
                    image.load()
                    self.assertEqual(image.format, 'PNG')
