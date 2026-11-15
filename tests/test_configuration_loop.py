"""A whole configuration is selected before one submission, including on restart."""

import asyncio
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import ANY, AsyncMock, Mock, patch
from uuid import uuid4

from jsonschema import ValidationError

from ax3l.app.snakelab.SnakeLabLoop import optimize, SimulationUnsuccessful, submit_draft
from ax3l.app.snakelab.SubmitSingleValueHandler import SubmitSingleValueHandler
from ax3l.app.snakelab.SubmitPairValuesHandler import SubmitPairValuesHandler
from ax3l.constants.DSimulationAnalysis import DSimulationAnalysis
from ax3l.constants.DChoice import CHOICE_LABELS
from ax3l.entities.ConfigurationDraft import ConfigurationDraft, PARAMETER_ORDER
from ax3l.entities.SimulationAnalysis import SimulationAnalysis
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


class MemoryExperiments:
    """Detached snapshots exercise the orchestration's persistence boundaries."""
    def __init__(self):
        self.saved = None
        self.analyses = {}
        self.comparisons = {}

    def draft(self, draft_id=None):
        return deepcopy(self.saved)

    def save_draft(self, draft):
        self.saved = deepcopy(draft)
        if draft.phase == 'completed':
            raise asyncio.CancelledError()

    def analysis(self, run_id):
        return self.analyses.get(run_id)

    def comparison(self, run_id):
        return self.comparisons.get(run_id)

    def submission_events(self, run_id):
        return {}


class ConfigurationLoopTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.gold, self.latest, self.best, self.run = [str(uuid4()) for _ in range(4)]
        self.config = SimulationConfiguration.defaults()
        self.store = MemoryExperiments()
        for run_id, score in ((self.gold, 20), (self.latest, 10), (self.best, 30)):
            config = deepcopy(self.config)
            if run_id == self.best:
                config['seed'] += 1
            self.store.analyses[run_id] = SimulationAnalysis(run_id, config, {'high_score': score},
                                                           'Scores rose during training. Loss fluctuated.')
        self.snake = Mock()
        self.snake.is_simulation_running.return_value = False
        self.snake.is_config_unique.return_value = True
        self.snake.get_latest_completed_run_id.return_value = self.latest
        self.snake.get_all_time_best_run_id.return_value = self.best
        self.snake.get_num_sims.return_value = 2
        self.snake.submit_simulation.return_value = self.run
        self.snake.get_run_result.side_effect = lambda run_id: {
            'status': 'completed', 'high_score': 25 if run_id == self.run else 20,
            'config': self.config}
        self.events = Mock()
        self.events.current_golden_config.return_value = {'process_id': self.gold}
        module = 'ax3l.app.snakelab.SnakeLabLoop.'
        self.enterContext(patch(module + 'SnakeLab', return_value=self.snake))
        self.enterContext(patch(module + 'ExperimentDb', return_value=self.store))
        self.enterContext(patch(module + 'EventLogDb', return_value=self.events))
        self.rotation = self.enterContext(patch(module + 'rotate_if_needed', new_callable=AsyncMock))
        self.wait = self.enterContext(patch(module + 'wait_for_run', new_callable=AsyncMock))
        self.analysis = self.enterContext(patch(module + 'analyze_run', new_callable=AsyncMock))
        self.analysis.side_effect = lambda *args: self.store.analysis(args[5])
        self.tools = self.enterContext(patch(module + 'SnakeLabTools', return_value=AsyncMock()))
        self.conversation = self.enterContext(patch(module + 'converse', new_callable=AsyncMock))
        shared = 'ax3l.app.snakelab.SubmitSingleValueHandler.'
        self.enterContext(patch(shared + 'ExperimentDb', return_value=self.store))
        self.enterContext(patch(shared + 'SnakeLab', return_value=self.snake))
        self.db = Mock()
        self.prompts = []
        self.values = dict(hidden_size=240, sequence_length=12, batch_size=26,
                           learning_rate=.003, gamma=.97, epsilon_pair=(.91, .95),
                           reward_pair=(.25, -.5), epsilon_nice_pair=(.01, 40))

        async def select(llm, output, db, tools, prompts, *, parameter, process_id):
            self.snake.submit_simulation.assert_not_called()
            self.prompts.append(prompts[-1].to_md())
            value = self.values[parameter]
            payload = {'draft_id': process_id}
            if isinstance(value, tuple):
                payload.update(pair=parameter, value_1=value[0], value_2=value[1])
                result = SubmitPairValuesHandler(db).submit(payload)
            else:
                payload.update(parameter=parameter, value=value)
                result = SubmitSingleValueHandler(db).submit(payload)
            self.assertEqual(result['status'], 'ok')
            return result

        self.conversation.side_effect = select

    async def cycle(self):
        with self.assertRaises(asyncio.CancelledError):
            await optimize(Mock(), Path('/tmp'), self.db, 'endpoint')

    def draft(self, count=0, phase='choosing'):
        return ConfigurationDraft(str(uuid4()), self.gold,
                                  {'latest': self.latest, 'golden': self.gold, 'all_time_best': self.best},
                                  deepcopy(self.config), PARAMETER_ORDER[:count], phase)

    async def test_eight_choices_then_exactly_one_simulation_with_all_changes(self):
        await self.cycle()
        self.assertEqual([call.kwargs['parameter'] for call in self.conversation.await_args_list], PARAMETER_ORDER)
        candidate = self.snake.submit_simulation.call_args.args[0]
        self.assertEqual(candidate['model']['hidden_size'], 240)
        self.assertEqual(candidate['training']['sequence_length'], 12)
        self.assertEqual(candidate['training']['batch_size'], 26)
        self.assertEqual(candidate['training']['learning_rate'], .003)
        self.assertEqual(candidate['training']['gamma'], .97)
        self.assertEqual(candidate['epsilon']['initial'], .91)
        self.assertEqual(candidate['game']['rewards']['closer_to_food'], .25)
        self.assertEqual(candidate['epsilon_nice'], {'probability': .01, 'steps': 40})
        self.snake.submit_simulation.assert_called_once()
        self.wait.assert_awaited_once_with(self.snake, self.db, self.run)
        self.assertEqual(self.store.saved.phase, 'completed')
        for parameter, prompt in zip(PARAMETER_ORDER, self.prompts):
            self.assertIn(f'Choose {CHOICE_LABELS[parameter]}.', prompt)
            self.assertIn('data_tool', prompt)
            self.assertIn('/draft', prompt)
            self.assertLess(len(prompt.split()), 75)
            for run_id in (self.gold, self.latest, self.best):
                self.assertNotIn(run_id.split('-')[0], prompt)

    async def test_restart_resumes_at_the_first_unselected_parameter(self):
        self.store.saved = self.draft(3)
        self.store.saved.config['model']['hidden_size'] = 272
        await self.cycle()
        self.assertEqual([call.kwargs['parameter'] for call in self.conversation.await_args_list], PARAMETER_ORDER[3:])
        self.assertEqual(self.snake.submit_simulation.call_args.args[0]['model']['hidden_size'], 272)
        self.assertEqual(self.rotation.await_count, 1)  # Resume pending rotation only.

    async def check_image_analysis_before_choices(self, completed_choices=0):
        if completed_choices:
            self.store.saved = self.draft(completed_choices)
            self.store.saved.config['model']['hidden_size'] = 272
        references = [self.latest, self.gold, self.best]
        completed = deepcopy(self.store.analyses)
        self.store.analyses.clear()
        analyzed = []
        for index, analysis in enumerate(completed.values(), 1):
            completed[analysis.run_id] = SimulationAnalysis(
                analysis.run_id, analysis.config, analysis.metrics,
                '\n'.join(f'{label}: Reference {index} observation.'
                          for label in DSimulationAnalysis.SECTIONS.values()))

        async def analyze(*args):
            run_id = args[5]
            if run_id in references:
                self.assertEqual(self.store.saved.phase, 'preparing')
                self.assertEqual(self.prompts, [])
                analyzed.append(run_id)
                self.store.analyses[run_id] = completed[run_id]
            return self.store.analysis(run_id)

        self.analysis.side_effect = analyze
        select = self.conversation.side_effect

        async def choose(*args, **kwargs):
            self.assertEqual(analyzed, references)
            for run_id in references:
                self.assertEqual(self.store.analysis(run_id), completed[run_id])
            self.assertIn('data_tool', args[4][-1].to_md())
            self.assertNotIn('Reference 1 observation.', args[4][-1].to_md())
            return await select(*args, **kwargs)

        self.conversation.side_effect = choose
        await self.cycle()
        self.assertEqual([call.kwargs['parameter'] for call in self.conversation.await_args_list],
                         PARAMETER_ORDER[completed_choices:])
        if completed_choices:
            self.assertEqual(self.snake.submit_simulation.call_args.args[0]['model']['hidden_size'], 272)

    async def test_image_observations_are_ready_to_browse_before_every_choice(self):
        await self.check_image_analysis_before_choices()

    async def test_restart_finishes_image_jobs_before_the_next_config_prompt(self):
        await self.check_image_analysis_before_choices(completed_choices=3)

    async def test_reference_preparation_is_durable_and_resumes_before_choices(self):
        self.store.saved = self.draft(phase='preparing')
        original = deepcopy(self.store.saved)
        self.analysis.side_effect = asyncio.CancelledError()
        await self.cycle()
        self.assertEqual(self.store.saved, original)
        self.analysis.assert_awaited_once_with(self.snake, ANY, ANY,
                                               self.db, 'endpoint', self.latest, 20)
        self.conversation.assert_not_awaited()
        self.snake.submit_simulation.assert_not_called()
        self.snake.get_latest_completed_run_id.assert_not_called()

    async def test_interrupted_reference_analysis_preserves_resumed_choices(self):
        self.store.saved = self.draft(3)
        self.store.saved.config['model']['hidden_size'] = 272
        original = deepcopy(self.store.saved)
        original.phase = 'preparing'
        self.analysis.side_effect = asyncio.CancelledError()
        await self.cycle()
        self.assertEqual(self.store.saved, original)
        self.conversation.assert_not_awaited()
        self.snake.submit_simulation.assert_not_called()

    async def test_restart_after_final_choice_does_not_repeat_any_conversation(self):
        self.store.saved = self.draft(8, 'ready')
        await self.cycle()
        self.conversation.assert_not_awaited()
        self.snake.submit_simulation.assert_called_once()

    async def test_restart_reconciles_a_lost_submission_reply_without_resubmitting(self):
        self.store.saved = self.draft(8, 'submitting')
        self.snake.find_config_run.return_value = self.run
        await self.cycle()
        self.snake.submit_simulation.assert_not_called()
        self.snake.find_config_run.assert_called_once_with(self.store.saved.config)
        self.wait.assert_awaited_once()
        self.conversation.assert_not_awaited()

    async def test_ambiguous_unrecorded_submission_stops_without_retry(self):
        self.store.saved = self.draft(8, 'submitting')
        self.snake.find_config_run.return_value = None
        with self.assertRaisesRegex(RuntimeError, 'will not be retried'):
            await optimize(Mock(), Path('/tmp'), self.db, 'endpoint')
        self.snake.submit_simulation.assert_not_called()
        self.wait.assert_not_awaited()

    async def test_submitted_run_is_not_submitted_again(self):
        self.store.saved = self.draft(8, 'submitted')
        self.store.saved.run_id = self.run
        await self.cycle()
        self.snake.submit_simulation.assert_not_called()
        self.wait.assert_awaited_once_with(self.snake, self.db, self.run)

    async def test_cancelled_simulation_is_marked_failed_without_comparison(self):
        self.store.saved = self.draft(8, 'submitted')
        self.store.saved.run_id = self.run
        self.wait.side_effect = SimulationUnsuccessful('cancelled')
        with self.assertRaises(SimulationUnsuccessful):
            await optimize(Mock(), Path('/tmp'), self.db, 'endpoint')
        self.assertEqual(self.store.saved.phase, 'failed')
        self.analysis.assert_not_awaited()
        self.assertNotIn('configuration_compared', [call.args[0] for call in self.db.log.call_args_list])

    async def test_one_reference_analysis_when_a_run_fills_all_three_roles(self):
        self.snake.get_latest_completed_run_id.return_value = self.gold
        self.snake.get_all_time_best_run_id.return_value = self.gold
        await self.cycle()
        self.assertEqual([call.args[5] for call in self.analysis.await_args_list], [self.gold, self.run])
        self.assertEqual(len(self.prompts), len(PARAMETER_ORDER))

    async def test_recorded_comparison_resumes_analysis_without_comparing_again(self):
        self.store.saved = self.draft(8, 'submitted')
        self.store.saved.run_id = self.run
        self.store.comparisons[self.run] = {'current_golden_run_id': self.run,
                                           'reason': 'Improved', 'event_id': 123}
        self.events.current_golden_config.return_value = {'process_id': self.run}
        await self.cycle()
        self.assertNotIn('configuration_compared', [call.args[0] for call in self.db.log.call_args_list])
        self.analysis.assert_awaited_once()

    async def test_new_draft_uses_the_rotated_baseline_before_parameter_selection(self):
        rotated = self.store.analyses[self.best]
        async def rotate(*args, resume_only=False):
            if not resume_only:
                self.events.current_golden_config.return_value = {'process_id': self.best}
        self.rotation.side_effect = rotate
        self.snake.get_run_result.return_value = None
        self.snake.get_run_result.side_effect = lambda run_id: dict(
            status='completed', high_score=30, config=rotated.config)
        self.conversation.side_effect = asyncio.CancelledError()
        await self.cycle()
        self.assertEqual(self.store.saved.golden_run_id, self.best)
        self.assertEqual(self.store.saved.config['seed'], self.config['seed'] + 1)
        prompt = self.conversation.await_args.args[4][-1].to_md()
        self.assertIn("beat golden's 30 points", prompt)

    def test_ready_drafts_cannot_submit_epsilon_nice_values_above_either_cap(self):
        for probability, steps in ((.1, 51), (.11, 50)):
            with self.subTest(probability=probability, steps=steps):
                draft = self.draft(8, 'ready')
                draft.config['epsilon_nice'].update(probability=probability, steps=steps)
                original = deepcopy(draft)
                with self.assertRaises(ValidationError):
                    submit_draft(self.snake, self.db, self.store, draft)
                self.assertEqual(draft, original)
                self.assertIsNone(self.store.saved)
        self.snake.submit_simulation.assert_not_called()
        self.db.log.assert_not_called()

    def test_submission_intent_survives_transport_failure(self):
        draft = self.draft(8, 'ready')
        self.snake.submit_simulation.side_effect = TimeoutError('lost reply')
        with self.assertRaises(TimeoutError):
            submit_draft(self.snake, self.db, self.store, draft)
        self.assertEqual(self.store.saved.phase, 'submitting')
        self.snake.submit_simulation.assert_called_once()
