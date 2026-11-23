"""Exact episode statistics and simulation charts."""

from copy import deepcopy
import unittest
from unittest.mock import patch
from uuid import uuid4

from ax3l.activity.RunAnalysis import measure, render_analysis
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


def observations():
    return [dict(episode=index, score=score, steps=10, epsilon=epsilon, loss=loss,
                 outcome=outcome, epsilon_injections=1, epsilon_nice_injections=2)
            for index, (score, epsilon, loss, outcome) in enumerate((
                (0, .9, None, 'wall'), (2, .5, .8, 'snake'), (4, 0, .4, 'max_moves'),
                (6, 0, .2, 'board_filled'), (3, 0, None, None)), 1)]


class RunAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.run_id = str(uuid4())
        self.config = SimulationConfiguration.defaults()
        self.episodes = observations()
        self.metrics = measure(self.episodes, 6)

    def test_exact_statistics_include_rare_high_scores_and_unrecorded_outcomes(self):
        self.assertEqual(self.metrics['episodes'], 5)
        self.assertEqual(self.metrics['high_score'], 6)
        self.assertEqual(self.metrics['mean_score'], 3)
        self.assertEqual(self.metrics['median_score'], 3)
        self.assertEqual(self.metrics['mean_first_50_scores'], 3)
        self.assertEqual(self.metrics['mean_last_50_scores'], 3)
        self.assertEqual(self.metrics['zero_score_episodes'], 1)
        self.assertEqual(self.metrics['high_score_episodes'], 1)
        self.assertEqual(self.metrics['episodes_with_loss'], 3)
        self.assertEqual(self.metrics['total_steps'], 50)
        for category in ('wall', 'snake', 'max_moves', 'board_filled', 'unrecorded_or_other'):
            self.assertEqual(self.metrics['termination_reasons'][category], {'count': 1, 'percent': 20})
        self.assertEqual(sum(row['percent'] for row in self.metrics['termination_reasons'].values()), 100)
        self.assertEqual(self.metrics['epsilon_random_actions'], 5)
        self.assertEqual(self.metrics['nice_overrides'], 10)

    def test_empty_observations_do_not_invent_score_averages(self):
        metrics = measure([], 0)
        self.assertIsNone(metrics['mean_score'])
        self.assertIsNone(metrics['median_score'])
        self.assertIsNone(metrics['mean_first_50_scores'])
        self.assertIsNone(metrics['mean_last_50_scores'])
        self.assertEqual(metrics['termination_reasons']['wall']['percent'], 0)

    def test_score_comparison_supplies_both_window_means_without_using_the_run_average(self):
        for first, last in ((1, 3), (3, 1), (2, 2)):
            with self.subTest(first=first, last=last):
                scores = [first] * 50 + [9] * 400 + [last] * 50
                episodes = [dict(self.episodes[0], episode=index, score=score)
                            for index, score in enumerate(scores, 1)]
                metrics = measure(episodes, 9)
                self.assertEqual(metrics['mean_first_50_scores'], first)
                self.assertEqual(metrics['mean_last_50_scores'], last)
                self.assertNotEqual(metrics['mean_score'], first)
                self.assertNotEqual(metrics['mean_score'], last)

    def render(self, section, episodes=None, *, golden_episodes=None):
        figures = []
        def capture(figure, **kwargs):
            figures.append(figure)
            return b'png'
        episodes = self.episodes if episodes is None else episodes
        with patch('plotly.graph_objects.Figure.to_image', capture):
            self.assertEqual(render_analysis(self.config, episodes,
                                            measure(episodes, 6), 9, section,
                                            golden_episodes=golden_episodes), b'png')
        figure = figures[0]
        self.assertNotIn(self.run_id.split('-')[0], figure.layout.title.text)
        self.assertIn('Goal:', figure.layout.title.text)
        self.assertNotIn('xaxis2', figure.layout.to_plotly_json())
        return figure

    def test_three_images_have_separate_axes_and_no_unrelated_traces(self):
        scores = self.render('scores')
        self.assertEqual([trace.name for trace in scores.data], ['Episode score', 'Trailing mean (up to 20 episodes)'])
        self.assertIn('points', scores.layout.yaxis.title.text)
        self.assertEqual(len(scores.layout.shapes), 2)
        self.assertEqual(scores.layout.shapes[0].y0, 9)
        distribution = self.render('distribution')
        self.assertEqual(len(distribution.data), 1)
        self.assertEqual(distribution.data[0].type, 'bar')
        self.assertEqual(list(distribution.data[0].x), [0, 2, 3, 4, 6])
        self.assertEqual(list(distribution.data[0].y), [1] * 5)
        self.assertEqual(len(distribution.layout.shapes), 0)
        self.assertIn('episodes', distribution.layout.yaxis.title.text)
        loss = self.render('loss')
        self.assertEqual(len(loss.data), 2)
        self.assertIn('Smooth L1', loss.layout.yaxis.title.text)
        self.assertEqual(list(loss.data[0].y), [None, .8, .4, .2, None])
        self.assertFalse(loss.data[0].connectgaps)

    def test_loss_mean_uses_twenty_episodes_and_preserves_missing_and_zero_losses(self):
        losses = [100] + [0] * 19 + [20, None, 0]
        episodes = [dict(self.episodes[0], episode=index, loss=loss)
                    for index, loss in enumerate(losses, 1)]
        figure = self.render('loss', episodes)
        raw, smoothed = figure.data
        self.assertEqual(list(raw.y), losses)
        self.assertEqual(smoothed.y[0], 100)
        self.assertEqual(smoothed.y[1], 50)
        self.assertEqual(smoothed.y[19], 5)
        self.assertEqual(smoothed.y[20], 1)
        self.assertIsNone(smoothed.y[21])
        self.assertAlmostEqual(smoothed.y[22], 20 / 19)
        self.assertFalse(smoothed.connectgaps)
        self.assertLess(raw.opacity, 1)
        self.assertLess(raw.line.width, smoothed.line.width)

    def test_golden_loss_has_its_own_mean_color_and_episode_axis(self):
        golden = [dict(self.episodes[0], episode=index, loss=2 if index == 1 else 0)
                  for index in range(1, 61)]
        original = deepcopy((self.episodes, golden))
        figure = self.render('loss', golden_episodes=golden)
        raw, smoothed, golden_raw, golden_mean = figure.data
        self.assertEqual(list(raw.x), [1, 2, 3, 4, 5])
        self.assertEqual(list(golden_raw.x), list(range(1, 61)))
        self.assertEqual(golden_mean.x, golden_raw.x)
        self.assertEqual(list(golden_raw.y), [2] + [0] * 59)
        self.assertEqual(golden_mean.y[0], 2)
        self.assertEqual(golden_mean.y[1], 1)
        self.assertEqual(golden_mean.y[-1], 0)
        self.assertEqual(raw.line.color, smoothed.line.color)
        self.assertEqual(golden_raw.line.color, golden_mean.line.color)
        self.assertNotEqual(smoothed.line.color, golden_mean.line.color)
        self.assertIn('Golden', golden_mean.name)
        self.assertEqual(figure.layout.xaxis.dtick, 10)
        self.assertEqual((self.episodes, golden), original)

    def test_missing_loss_is_labeled_without_inventing_zero_measurements(self):
        episodes = [dict(episode, loss=None) for episode in self.episodes]
        figure = self.render('loss', episodes)
        self.assertEqual(list(figure.data[0].y), [None] * 5)
        self.assertEqual(list(figure.data[1].y), [None] * 5)
        self.assertEqual(figure.layout.annotations[0].text, 'No training losses recorded')

    def test_endings_keep_all_episodes_as_denominator_and_only_round_display_labels(self):
        outcomes = ['snake'] * 528 + ['wall'] * 270 + ['max_moves'] * 194 + ['board_filled'] * 3 + [None] * 5
        episodes = [dict(self.episodes[0], episode=index, outcome=outcome)
                    for index, outcome in enumerate(outcomes, 1)]
        original = deepcopy(episodes)
        figure = self.render('endings', episodes)
        self.assertEqual(len(figure.data), 1)
        bars = figure.data[0]
        self.assertEqual(bars.orientation, 'h')
        self.assertEqual(list(bars.y), ['Snake collision', 'Wall collision', 'Max moves'])
        self.assertEqual(figure.layout.yaxis.autorange, 'reversed')
        self.assertEqual(list(figure.layout.yaxis.categoryarray), list(bars.y))
        self.assertEqual(list(bars.x), [52.8, 27, 19.4])
        self.assertEqual(list(bars.text), ['53% (528 episodes)', '27% (270 episodes)', '19% (194 episodes)'])
        self.assertFalse(bars.showlegend)
        self.assertIn('all 1000 episodes', figure.layout.annotations[0].text)
        self.assertIn('3 board filled; 5 unrecorded or other', figure.layout.annotations[0].text)
        self.assertEqual(episodes, original)

    def test_endings_keep_zero_reasons_and_a_fixed_percent_axis_even_for_empty_runs(self):
        for episodes, values in (([], [0, 0, 0]), (self.episodes[:1], [0, 100, 0])):
            with self.subTest(episodes=len(episodes)):
                figure = self.render('endings', episodes)
                self.assertEqual(list(figure.data[0].x), values)
                self.assertEqual(len(figure.data[0].y), 3)
                self.assertEqual(figure.data[0].text[0], '0% (0 episodes)')
                self.assertEqual(list(figure.layout.xaxis.range), [0, 100])
                self.assertEqual(figure.layout.xaxis.dtick, 20)
                self.assertEqual(figure.layout.xaxis.ticksuffix, '%')
                self.assertEqual(figure.layout.xaxis.tickformat, '.0f')
                self.assertEqual(figure.data[0].textposition, 'outside')
                self.assertFalse(figure.data[0].cliponaxis)
                self.assertNotIn('Not shown:', figure.layout.annotations[0].text)
                if not episodes:
                    self.assertEqual(figure.layout.annotations[0].text, 'No episodes recorded.')
