"""Bounded chart tasks, exact observations, and resumable result handoff."""

from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, Mock, call, patch
from uuid import uuid4

from ax3l.activity.RunAnalysis import measure, render_analysis
from ax3l.app.snakelab.AnalyzeRun import analyze_run
from ax3l.app.snakelab.SubmitSimulationSummaryHandler import SubmitSimulationSummaryHandler
from ax3l.app.snakelab.prompts.AnalyzeSimulation import AnalyzeSimulation
from ax3l.constants.DSimulationAnalysis import DSimulationAnalysis
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
                prompt = AnalyzeSimulation(self.run_id, self.config, metrics, b'png', 'scores').to_md()
                self.assertIn('first 50 and final 50 episodes of this same run', prompt)
                self.assertIn('higher, lower, or equal', prompt)
                facts = json.loads(prompt.split('Measured facts: ')[1].split('\n')[0])
                self.assertEqual(facts, {'episodes': 500, 'mean_first_50_scores': first,
                                         'mean_last_50_scores': last})
                self.assertNotEqual(metrics['mean_score'], facts['mean_first_50_scores'])
                self.assertNotEqual(metrics['mean_score'], facts['mean_last_50_scores'])

    def render(self, section, episodes=None):
        figures = []
        def capture(figure, **kwargs):
            figures.append(figure)
            return b'png'
        episodes = self.episodes if episodes is None else episodes
        with patch('plotly.graph_objects.Figure.to_image', capture):
            self.assertEqual(render_analysis(self.run_id, self.config, episodes,
                                            measure(episodes, 6), 9, section), b'png')
        figure = figures[0]
        self.assertIn(self.run_id.split('-')[0], figure.layout.title.text)
        self.assertNotIn(self.run_id, figure.layout.title.text)
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
        self.assertEqual(len(loss.data), 1)
        self.assertIn('Smooth L1', loss.layout.yaxis.title.text)
        self.assertEqual(list(loss.data[0].y), [None, .8, .4, .2, None])
        self.assertFalse(loss.data[0].connectgaps)

    def test_missing_loss_is_labeled_without_inventing_zero_measurements(self):
        episodes = [dict(episode, loss=None) for episode in self.episodes]
        figure = self.render('loss', episodes)
        self.assertEqual(list(figure.data[0].y), [None] * 5)
        self.assertEqual(figure.layout.annotations[0].text, 'No training losses recorded')

    def test_each_prompt_has_one_image_one_question_and_an_explicit_example(self):
        for section in DSimulationAnalysis.SECTIONS:
            with self.subTest(section=section):
                prompt = AnalyzeSimulation(self.run_id, self.config, self.metrics, b'png', section)
                message = json.loads(prompt.to_json())
                self.assertEqual([part['type'] for part in message['content']], ['text', 'image_url'])
                self.assertEqual(message['content'][1]['image_url']['url'], 'data:image/png;base64,cG5n')
                text = message['content'][0]['text']
                self.assertIn('at most 40 words', text)
                self.assertIn('submit_simulation_summary', text)
                self.assertIn('Example format (invented data', text)
                self.assertIn('/analysis/' + section, text)
                self.assertNotIn('Configuration:', text)
                self.assertNotIn('termination_reasons', text)
                self.assertNotIn(self.run_id, text)
                self.assertLess(len(text.split()), 190)
                facts = json.loads(text.split('Measured facts: ')[1].split('\n')[0])
                if section == 'loss':
                    self.assertEqual(facts, {'episodes': 5, 'episodes_with_loss': 3})
                else:
                    self.assertNotIn('episodes_with_loss', facts)


class SummarySubmissionTests(unittest.TestCase):
    def setUp(self):
        module = 'ax3l.app.snakelab.SubmitSimulationSummaryHandler.'
        self.experiments = self.enterContext(patch(module + 'ExperimentDb')).return_value
        self.experiments.analysis.return_value = None
        self.sections = {}
        self.experiments.analysis_sections.side_effect = lambda run_id: deepcopy(self.sections)
        self.experiments.save_analysis_sections.side_effect = lambda run_id, sections: self.sections.update(sections)
        self.snake = self.enterContext(patch(module + 'SnakeLab')).return_value
        self.snake.get_run_result.return_value = dict(status='completed', high_score=6,
                                                     config=SimulationConfiguration.defaults())
        self.snake.get_analysis_episodes.return_value = observations()
        self.handler = SubmitSimulationSummaryHandler(Mock())
        self.run_id = str(uuid4())

    def submit(self, section='scores', text='Scores stayed low.'):
        return self.handler.submit({'run_id': self.run_id, 'section': section, 'summary': text})

    def test_each_section_is_saved_and_all_three_carry_into_the_final_analysis(self):
        summaries = {'scores': 'Scores averaged 3 points.', 'distribution': 'The high score was rare.',
                     'loss': 'Recorded losses declined with gaps.'}
        for section in ('distribution', 'scores'):
            self.assertEqual(self.submit(section, summaries[section])['status'], 'ok')
            self.experiments.save_analysis.assert_not_called()
            self.snake.get_analysis_episodes.assert_not_called()
        self.assertEqual(self.submit('loss', summaries['loss'])['status'], 'ok')
        saved = self.experiments.save_analysis.call_args.args[0]
        self.assertEqual(saved.run_id, self.run_id)
        self.assertEqual(saved.metrics['mean_score'], 3)
        self.assertEqual(saved.summary, '\n'.join(f'{label}: {summaries[section]}'
                         for section, label in DSimulationAnalysis.SECTIONS.items()))
        self.assertEqual(self.handler.submit({'run_id': self.run_id, 'section': 'loss',
                                             'summary': 'Loss fell.', 'metrics': {}})['status'], 'rejected')

    def test_repeated_partial_submission_keeps_its_first_accepted_observation(self):
        self.submit(text='Original observation.')
        self.submit(text='Replacement observation.')
        self.assertEqual(self.sections, {'scores': 'Original observation.'})
        self.experiments.save_analysis_sections.assert_called_once()

    def test_invalid_text_ids_and_sections_are_rejected_before_observation_reads(self):
        for text in ('', 'A. B. C.', 'a' * 1001, True, ' '.join(['word'] * 41)):
            with self.subTest(summary=text):
                self.assertEqual(self.submit(text=text)['code'], 'invalid_summary')
        for run_id in (None, 12, 'bad-id'):
            self.assertEqual(self.handler.submit({'run_id': run_id, 'section': 'loss',
                                                 'summary': 'Loss fell.'})['status'], 'rejected')
        for section in ('unknown', None, []):
            self.assertEqual(self.submit(section)['status'], 'rejected')
        self.snake.get_run_result.assert_not_called()
        self.experiments.save_analysis.assert_not_called()

    def test_incomplete_runs_are_not_analyzed(self):
        self.snake.get_run_result.return_value['status'] = 'running'
        self.assertEqual(self.submit()['status'], 'rejected')
        self.experiments.save_analysis_sections.assert_not_called()

    def test_repeated_final_submission_keeps_the_saved_analysis(self):
        self.experiments.analysis.return_value = SimulationAnalysis(self.run_id, {}, {}, 'Saved.')
        self.assertEqual(self.submit()['status'], 'ok')
        self.experiments.save_analysis.assert_not_called()
        self.experiments.save_analysis_sections.assert_not_called()
        self.snake.get_run_result.assert_not_called()

    def test_failed_final_save_leaves_the_last_section_unfinished_for_restart(self):
        self.sections.update(scores='Scores stayed flat.', distribution='High scores were rare.')
        self.experiments.save_analysis.side_effect = RuntimeError('write failed')
        with self.assertRaisesRegex(RuntimeError, 'write failed'):
            self.submit('loss', 'Loss fell.')
        self.assertNotIn('loss', self.sections)
        self.experiments.save_analysis.side_effect = None
        self.assertEqual(self.submit('loss', 'Loss fell.')['status'], 'ok')
        self.assertEqual(self.experiments.save_analysis.call_count, 2)
        self.assertIn('Training loss: Loss fell.', self.experiments.save_analysis.call_args.args[0].summary)


class AnalyzeRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_cached_analysis_does_not_render_or_call_the_llm_again(self):
        module = 'ax3l.app.snakelab.AnalyzeRun.'
        saved = SimulationAnalysis('run', {}, {}, 'Saved.')
        with patch(module + 'ExperimentDb') as experiments, patch(module + 'render_analysis') as render:
            experiments.return_value.analysis.return_value = saved
            snake, llm = Mock(), Mock()
            self.assertIs(await analyze_run(snake, llm, Path('/tmp'), Mock(), 'endpoint', 'run', 10), saved)
            snake.get_run_result.assert_not_called()
            render.assert_not_called()
            llm.complete.assert_not_called()
            experiments.return_value.save_analysis_task.assert_not_called()

    async def check_sections(self, completed):
        module = 'ax3l.app.snakelab.AnalyzeRun.'
        run_id = str(uuid4())
        saved = SimulationAnalysis(run_id, {}, {}, 'Saved.')
        snake = Mock()
        snake.get_run_result.return_value = dict(status='completed', high_score=6,
                                                 config=SimulationConfiguration.defaults())
        snake.get_analysis_episodes.return_value = observations()
        with patch(module + 'ExperimentDb') as experiments, \
                patch(module + 'render_analysis', side_effect=lambda *args: args[-1].encode()) as render, \
                patch(module + 'SnakeLabTools', return_value=AsyncMock()) as tools, \
                patch(module + 'converse', new_callable=AsyncMock) as conversation:
            experiments.return_value.analysis.side_effect = [None, saved]
            experiments.return_value.analysis_sections.return_value = completed
            self.assertIs(await analyze_run(snake, Mock(), Path('/tmp'), Mock(), 'endpoint', run_id, 10), saved)
            pending = [section for section in DSimulationAnalysis.SECTIONS if section not in completed]
            self.assertEqual(tools.call_args_list, [call('endpoint', 'simulation_summary', run_id=run_id,
                                                       section=section) for section in pending])
            self.assertEqual(render.call_count, len(pending))
            self.assertEqual(conversation.await_count, len(pending))
            recorded = [entry.args[0] for entry in experiments.return_value.save_analysis_task.call_args_list]
            self.assertEqual([(task.section, task.phase) for task in recorded],
                             [(section, phase) for section in pending for phase in ('preparing', 'analyzing', 'saved')])
            images = []
            for entry in conversation.await_args_list:
                prompts = entry.args[4]
                self.assertEqual(len(prompts), 1)
                message = json.loads(prompts[0].to_json())
                images.append(message['content'][1]['image_url']['url'])
                self.assertEqual(entry.kwargs['process_id'], run_id)
            self.assertEqual(len(set(images)), len(pending))

    async def test_three_fresh_conversations_each_get_only_their_own_chart(self):
        await self.check_sections({})

    async def test_restart_resumes_after_the_last_saved_section(self):
        await self.check_sections({'scores': 'Scores stayed flat.'})

    async def test_image_failure_and_cancellation_are_recorded_and_propagate(self):
        import asyncio

        module = 'ax3l.app.snakelab.AnalyzeRun.'
        for error, phase in [(RuntimeError('inference unavailable'), 'failed'),
                              (asyncio.CancelledError(), 'stopped')]:
            with self.subTest(phase=phase), patch(module + 'ExperimentDb') as experiments, \
                    patch(module + 'render_analysis', return_value=b'png'), \
                    patch(module + 'SnakeLabTools', return_value=AsyncMock()), \
                    patch(module + 'converse', side_effect=error):
                experiments.return_value.analysis.return_value = None
                experiments.return_value.analysis_sections.return_value = {}
                snake = Mock()
                snake.get_run_result.return_value = dict(status='completed', high_score=6,
                                                         config=SimulationConfiguration.defaults())
                snake.get_analysis_episodes.return_value = observations()
                with self.assertRaises(type(error)):
                    await analyze_run(snake, Mock(), Path('/tmp'), Mock(), 'endpoint', 'run', 10)
                self.assertEqual(experiments.return_value.save_analysis_task.call_args.args[0].phase, phase)
