"""Verify score windows and the PNG guides the vision model reads."""

from base64 import b64decode
from copy import deepcopy
from io import BytesIO
import unittest

from PIL import Image

from ax3l.activity.ExplorationProgress import exploration_progress
from ax3l.activity.RewardProgress import reward_progress
from ax3l.activity.ScorePercentiles import score_percentiles
from ax3l.activity.TrainingProgress import training_progress
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

    def test_default_windows_cover_150_epochs_with_a_final_partial_window(self):
        points = score_percentiles([dict(episode=i, score=0) for i in range(1, 322)])
        self.assertEqual(points, [dict(epoch=epoch, p90=0, p25=0) for epoch in (150, 300, 321)])
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


class RewardProgressTests(unittest.TestCase):
    def test_weights_food_and_terminal_collisions_by_total_moves_in_epoch_order(self):
        episodes = [dict(episode=3, score=3, steps=60, outcome='max_moves'),
                    dict(episode=2, score=9, steps=90, outcome='snake'),
                    dict(episode=1, score=1, steps=10, outcome='wall')]
        original = deepcopy(episodes)
        self.assertEqual(reward_progress(episodes, window_size=2), [
            dict(epoch=2, food=10, wall=1, snake=1),
            dict(epoch=3, food=5, wall=0, snake=0),
        ])
        self.assertEqual(episodes, original)
        self.assertEqual(reward_progress([]), [])

    def test_missing_outcomes_leave_collision_gaps_and_zero_moves_leave_all_rate_gaps(self):
        self.assertEqual(reward_progress([
            dict(episode=1, score=2, steps=20, outcome='wall'),
            dict(episode=2, score=2, steps=20, outcome=None),
            dict(episode=3, score=0, steps=0, outcome='snake'),
        ], window_size=2), [
            dict(epoch=2, food=10, wall=None, snake=None),
            dict(epoch=3, food=None, wall=None, snake=None),
        ])

    def test_default_windows_cover_150_epochs_with_final_partial_window(self):
        episodes = [dict(episode=i, score=1, steps=100, outcome='wall') for i in range(1, 322)]
        self.assertEqual(reward_progress(episodes), [
            dict(epoch=epoch, food=1, wall=1, snake=0) for epoch in (150, 300, 321)
        ])


class TrainingProgressTests(unittest.TestCase):
    def test_averages_recorded_losses_in_epoch_order_including_zero_and_keeps_gaps(self):
        episodes = [dict(episode=i, loss=loss) for i, loss in reversed(list(enumerate(
            (None, 0, .6, None, None, None, 2.4), 1)))]
        original = deepcopy(episodes)
        self.assertEqual(training_progress(episodes, window_size=3), [
            dict(epoch=3, loss=.3), dict(epoch=6, loss=None), dict(epoch=7, loss=2.4),
        ])
        self.assertEqual(episodes, original)
        self.assertEqual(training_progress([]), [])

    def test_default_150_epoch_windows_retain_final_partial_window(self):
        episodes = [dict(episode=i, loss=.5 if i <= 150 else 0 if i <= 300 else 2)
                    for i in range(1, 322)]
        self.assertEqual(training_progress(episodes), [
            dict(epoch=150, loss=.5), dict(epoch=300, loss=0), dict(epoch=321, loss=2),
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

    def test_architecture_uses_150_epoch_windows_and_shared_axes_without_extending_shorter_run(self):
        golden = [dict(episode=i, score=10) for i in range(1, 215)]
        latest = [dict(episode=i, score=20) for i in range(1, 322)]
        url = run_comparison_image(VIEWS['architecture'], golden, latest)
        with Image.open(BytesIO(b64decode(url.split(',')[1]))) as image:
            for top, bottom in ((178, 378), (452, 652)):
                pixels = {color for _, color in image.crop((118, top, 1008, bottom + 4)).getcolors(200000)}
                self.assertIn((77, 179, 255), pixels)
                self.assertIn((255, 189, 112), pixels)
                # Both runs start at epoch 150, without checkpoints from smaller windows.
                early_pixels = {color for _, color in image.crop((128, top, 520, bottom + 4)).getcolors(200000)}
                self.assertNotIn((77, 179, 255), early_pixels)
                self.assertNotIn((255, 189, 112), early_pixels)
                self.assertEqual(image.getpixel((532, top)), (77, 179, 255))
                self.assertEqual(image.getpixel((532, (top + bottom) // 2)), (255, 189, 112))
                # The shared score ceiling is 20; golden ends at epoch 214, score 10.
                self.assertEqual(image.getpixel((709, (top + bottom) // 2)), (255, 189, 112))
                self.assertNotEqual(image.getpixel((900, (top + bottom) // 2)), (255, 189, 112))
                # Latest retains its final partial window, ending at epoch 321.
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

    def test_reward_comparison_has_three_shared_rate_panels_and_both_score_percentiles(self):
        golden = [dict(episode=i, score=10, steps=100, outcome='wall') for i in range(1, 301)]
        latest = [dict(episode=i, score=20, steps=100, outcome='snake') for i in range(1, 451)]
        url = run_comparison_image(VIEWS['reward-signals'], golden, latest)
        with Image.open(BytesIO(b64decode(url.split(',')[1]))) as image:
            self.assertEqual(image.size, (1056, 1254))
            # Food rates use the same ceiling of 20 as both collision panels.
            self.assertEqual(image.getpixel((709, 263)), (255, 189, 112))
            self.assertEqual(image.getpixel((1004, 178)), (77, 179, 255))
            self.assertEqual(image.getpixel((709, 593)), (255, 189, 112))
            self.assertEqual(image.getpixel((1004, 847)), (77, 179, 255))
            # Golden's score lines end at epoch 300; Latest reaches 450.
            self.assertEqual(image.getpixel((709, 1025)), (255, 189, 112))
            self.assertNotEqual(image.getpixel((900, 1025)), (255, 189, 112))
            self.assertEqual(image.getpixel((1004, 940)), (77, 179, 255))

    def test_reward_score_percentiles_have_distinct_solid_and_dashed_lines(self):
        episodes = [dict(episode=i, score=i % 10, steps=100, outcome='max_moves') for i in range(1, 601)]
        url = run_comparison_image(VIEWS['reward-signals'], [], episodes)
        with Image.open(BytesIO(b64decode(url.split(',')[1]))) as image:
            # 90th percentile 8.1 and 25th percentile 2 use a shared score ceiling of 9.
            solid_y = int(1110 - 170 * 8.1 / 9)
            dashed_y = int(1110 - 170 * 2 / 9)
            solid = [image.getpixel((x, solid_y)) for x in range(600, 900)]
            dashed = [image.getpixel((x, dashed_y)) for x in range(600, 900)]
            self.assertTrue(all(color == (77, 179, 255) for color in solid))
            self.assertIn((77, 179, 255), dashed)
            self.assertTrue(any(color != (77, 179, 255) for color in dashed))

    def test_missing_reward_measurements_do_not_draw_false_zero_collision_rates(self):
        for episodes in ([], [dict(episode=1, score=2, steps=20, outcome=None)],
                         [dict(episode=1, score=0, steps=0, outcome='wall')]):
            with self.subTest(episodes=episodes):
                url = run_comparison_image(VIEWS['reward-signals'], [], episodes)
                with Image.open(BytesIO(b64decode(url.split(',')[1]))) as image:
                    for top, bottom in ((432, 602), (686, 856)):
                        pixels = {color for _, color in image.crop((118, top, 1008, bottom + 4)).getcolors(200000)}
                        self.assertNotIn((77, 179, 255), pixels)

    def test_training_losses_share_an_axis_above_one_and_stop_at_each_runs_last_epoch(self):
        golden = [dict(episode=i, score=i % 10, loss=4) for i in range(1, 301)]
        latest = [dict(episode=i, score=i % 20, loss=2) for i in range(1, 451)]
        url = run_comparison_image(VIEWS['training'], golden, latest)
        with Image.open(BytesIO(b64decode(url.split(',')[1]))) as image:
            self.assertEqual(image.size, (1056, 768))
            # The shared loss ceiling is 4, with golden ending at epoch 300.
            self.assertEqual(image.getpixel((709, 452)), (255, 189, 112))
            self.assertNotEqual(image.getpixel((900, 452)), (255, 189, 112))
            self.assertEqual(image.getpixel((1004, 552)), (77, 179, 255))
            score_pixels = {color for _, color in image.crop((118, 178, 1008, 382)).getcolors(200000)}
            self.assertIn((77, 179, 255), score_pixels)
            self.assertIn((255, 189, 112), score_pixels)

    def test_training_score_panel_distinguishes_solid_90th_and_dashed_25th_percentiles(self):
        episodes = [dict(episode=i, score=i % 10, loss=.5) for i in range(1, 601)]
        url = run_comparison_image(VIEWS['training'], [], episodes)
        with Image.open(BytesIO(b64decode(url.split(',')[1]))) as image:
            solid_y = int(378 - 200 * 8.1 / 9)
            dashed_y = int(378 - 200 * 2 / 9)
            solid = [image.getpixel((x, solid_y)) for x in range(600, 900)]
            dashed = [image.getpixel((x, dashed_y)) for x in range(600, 900)]
            self.assertTrue(all(color == (77, 179, 255) for color in solid))
            self.assertIn((77, 179, 255), dashed)
            self.assertTrue(any(color != (77, 179, 255) for color in dashed))

    def test_training_loss_gaps_do_not_connect_windows_or_hide_a_measured_zero(self):
        episodes = [dict(episode=i, score=1, loss=None if i <= 150 or 300 < i <= 450
                         else 0 if i <= 300 else .4) for i in range(1, 601)]
        url = run_comparison_image(VIEWS['training'], [], episodes)
        with Image.open(BytesIO(b64decode(url.split(',')[1]))) as image:
            self.assertEqual(image.getpixel((561, 652)), (77, 179, 255))
            for left, right in ((335, 345), (700, 800)):
                pixels = {color for _, color in image.crop((left, 452, right, 656)).getcolors(100000)}
                self.assertNotIn((77, 179, 255), pixels)

    def test_empty_training_and_unmeasured_losses_do_not_draw_false_zero_losses(self):
        for episodes in ([], [dict(episode=1, score=1, loss=None)]):
            with self.subTest(episodes=episodes):
                url = run_comparison_image(VIEWS['training'], [], episodes)
                with Image.open(BytesIO(b64decode(url.split(',')[1]))) as image:
                    self.assertEqual(image.format, 'PNG')
                    pixels = {color for _, color in image.crop((118, 452, 1008, 656)).getcolors(200000)}
                    self.assertNotIn((77, 179, 255), pixels)
