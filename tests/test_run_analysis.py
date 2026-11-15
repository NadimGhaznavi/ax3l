"""Exact observations, reusable interpretations, and multimodal prompt contracts."""

import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from ax3l.activity.RunAnalysis import measure, render_analysis
from ax3l.app.snakelab.AnalyzeRun import analyze_run
from ax3l.app.snakelab.SubmitSimulationSummaryHandler import SubmitSimulationSummaryHandler
from ax3l.app.snakelab.prompts.AnalyzeSimulation import AnalyzeSimulation
from ax3l.entities.SimulationAnalysis import SimulationAnalysis
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

    def test_termination_percentages_use_all_episodes_and_keep_unrecorded_outcomes(self):
        self.assertEqual(self.metrics['episodes'], 5)
        self.assertEqual(self.metrics['high_score'], 6)
        self.assertEqual(self.metrics['mean_score'], 3)
        self.assertEqual(self.metrics['median_score'], 3)
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
        self.assertEqual(metrics['termination_reasons']['wall']['percent'], 0)

    def test_three_panel_chart_has_titles_units_target_and_missing_loss_gaps(self):
        figures = []
        def capture(figure, **kwargs):
            figures.append(figure)
            return b'png'
        with patch('plotly.graph_objects.Figure.to_image', capture):
            self.assertEqual(render_analysis(self.run_id, self.config, self.episodes, self.metrics, 9), b'png')
        figure = figures[0]
        self.assertIn(self.run_id.split('-')[0], figure.layout.title.text)
        self.assertNotIn(self.run_id, figure.layout.title.text)
        self.assertIn('Goal:', figure.layout.title.text)
        self.assertIn('points', figure.layout.yaxis.title.text)
        self.assertIn('episodes', figure.layout.yaxis2.title.text)
        self.assertIn('Smooth L1', figure.layout.yaxis3.title.text)
        self.assertEqual(list(figure.data[3].y), [None, .8, .4, .2, None])
        self.assertFalse(figure.data[3].connectgaps)
        self.assertEqual(len(figure.layout.shapes), 2)  # Target and end of ordinary epsilon.
        self.assertEqual(figure.layout.shapes[0].y0, 9)

    def test_png_and_exact_facts_are_sent_in_the_same_vision_message(self):
        prompt = AnalyzeSimulation(self.run_id, self.config, self.metrics, b'png')
        message = json.loads(prompt.to_json())
        self.assertEqual(message['content'][1], {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,cG5n'}})
        self.assertIn('termination_reasons', message['content'][0]['text'])
        self.assertIn('at most 80 words', message['content'][0]['text'])
        self.assertIn('submit_simulation_summary', message['content'][0]['text'])
        self.assertIn('Configuration:', message['content'][0]['text'])
        self.assertNotIn(self.run_id, message['content'][0]['text'])


class SummarySubmissionTests(unittest.TestCase):
    def setUp(self):
        module = 'ax3l.app.snakelab.SubmitSimulationSummaryHandler.'
        self.experiments = self.enterContext(patch(module + 'ExperimentDb')).return_value
        self.experiments.analysis.return_value = None
        self.snake = self.enterContext(patch(module + 'SnakeLab')).return_value
        self.snake.get_run_result.return_value = dict(status='completed', high_score=6,
                                                     config=SimulationConfiguration.defaults())
        self.snake.get_analysis_episodes.return_value = observations()
        self.handler = SubmitSimulationSummaryHandler(Mock())
        self.run_id = str(uuid4())

    def test_summary_is_saved_with_computed_facts_and_cannot_supply_its_own_numbers(self):
        text = 'Scores averaged 3.0 points. Training losses declined with gaps.'
        self.assertEqual(self.handler.submit({'run_id': self.run_id, 'summary': text}),
                         {'status': 'ok', 'analysis_run_id': self.run_id})
        saved = self.experiments.save_analysis.call_args.args[0]
        self.assertEqual(saved.run_id, self.run_id)
        self.assertEqual(saved.metrics['mean_score'], 3)
        self.assertEqual(saved.summary, text)
        self.assertEqual(self.handler.submit({'run_id': self.run_id, 'summary': text, 'metrics': {}})['status'], 'rejected')

    def test_invalid_text_and_ids_are_rejected_before_any_observation_read(self):
        for text in ('', 'One sentence.', 'A. B. C. D.', 'a' * 1001, True,
                     ' '.join(['word'] * 80) + '. Second sentence.'):
            with self.subTest(summary=text):
                self.assertEqual(self.handler.submit({'run_id': self.run_id, 'summary': text})['code'], 'invalid_summary')
        for run_id in (None, 12, 'bad-id'):
            self.assertEqual(self.handler.submit({'run_id': run_id, 'summary': 'A. B.'})['status'], 'rejected')
        self.snake.get_run_result.assert_not_called()
        self.experiments.save_analysis.assert_not_called()

    def test_incomplete_runs_are_not_analyzed(self):
        self.snake.get_run_result.return_value['status'] = 'running'
        self.assertEqual(self.handler.submit({'run_id': self.run_id, 'summary': 'Scores rose. Loss fell.'})['status'], 'rejected')
        self.experiments.save_analysis.assert_not_called()

    def test_a_repeated_submission_keeps_the_first_saved_interpretation(self):
        self.experiments.analysis.return_value = SimulationAnalysis(self.run_id, {}, {}, 'Saved. Unchanged.')
        self.assertEqual(self.handler.submit({'run_id': self.run_id, 'summary': 'New words. More words.'})['status'], 'ok')
        self.experiments.save_analysis.assert_not_called()
        self.snake.get_run_result.assert_not_called()


class AnalyzeRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_cached_analysis_does_not_render_or_call_the_llm_again(self):
        module = 'ax3l.app.snakelab.AnalyzeRun.'
        saved = SimulationAnalysis('run', {}, {}, 'Saved. Unchanged.')
        with patch(module + 'ExperimentDb') as experiments, patch(module + 'render_analysis') as render:
            experiments.return_value.analysis.return_value = saved
            snake, llm = Mock(), Mock()
            self.assertIs(await analyze_run(snake, llm, Path('/tmp'), Mock(), 'endpoint', 'run', 10), saved)
            snake.get_run_result.assert_not_called()
            render.assert_not_called()
            llm.complete.assert_not_called()

    async def test_new_analysis_uses_run_bound_summary_tool_and_multimodal_prompt(self):
        module = 'ax3l.app.snakelab.AnalyzeRun.'
        run_id = str(uuid4())
        saved = SimulationAnalysis(run_id, {}, {}, 'Scores rose. Loss fell.')
        snake = Mock()
        snake.get_run_result.return_value = dict(status='completed', high_score=6,
                                                 config=SimulationConfiguration.defaults())
        snake.get_analysis_episodes.return_value = observations()
        with patch(module + 'ExperimentDb') as experiments, \
                patch(module + 'render_analysis', return_value=b'png'), \
                patch(module + 'SnakeLabTools', return_value=AsyncMock()) as tools, \
                patch(module + 'converse', new_callable=AsyncMock) as conversation:
            experiments.return_value.analysis.side_effect = [None, saved]
            self.assertIs(await analyze_run(snake, Mock(), Path('/tmp'), Mock(), 'endpoint', run_id, 10), saved)
            tools.assert_called_once_with('endpoint', 'simulation_summary', run_id=run_id)
            prompt = conversation.await_args.args[4][-1]
            self.assertIn('image_url', prompt.to_json())
            self.assertEqual(conversation.await_args.kwargs['process_id'], run_id)
