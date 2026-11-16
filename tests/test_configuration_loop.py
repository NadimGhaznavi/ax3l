"""Qwen chooses parameters and decides when a unique draft should run, including on restart."""

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from jsonschema import ValidationError

from ax3l.app.snakelab.SnakeLabLoop import optimize, SimulationUnsuccessful, submit_draft
from ax3l.app.snakelab.SubmitSingleValueHandler import SubmitSingleValueHandler
from ax3l.app.snakelab.SubmitPairValuesHandler import SubmitPairValuesHandler
from ax3l.app.snakelab.SelectParameterHandler import SelectParameterHandler
from ax3l.app.snakelab.RunSimulationHandler import RunSimulationHandler
from ax3l.constants.DChoice import CHOICE_CHARTS, CHOICE_LABELS, REVISION_PARAMETER
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
            metrics = dict(high_score=score, episodes=500, episodes_with_loss=480,
                           mean_first_50_scores=.1, mean_last_50_scores=.2, epsilon_random_actions=95,
                           median_score=0, zero_score_episodes=463, high_score_episodes=1)
            self.store.analyses[run_id] = SimulationAnalysis(run_id, config, metrics, 'Previous notes.')
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
        self.analysis = self.enterContext(patch(module + 'record_run_metrics'))
        self.analysis.side_effect = lambda snake, experiments, run_id: experiments.analysis(run_id)
        self.chart = self.enterContext(patch(module + 'render_analysis', return_value=b'png'))
        self.tools = self.enterContext(patch(module + 'SnakeLabTools', return_value=AsyncMock()))
        self.conversation = self.enterContext(patch(module + 'converse', new_callable=AsyncMock))
        shared = 'ax3l.app.snakelab.SubmitSingleValueHandler.'
        self.enterContext(patch(shared + 'ExperimentDb', return_value=self.store))
        self.enterContext(patch(shared + 'SnakeLab', return_value=self.snake))
        self.enterContext(patch('ax3l.app.snakelab.SelectParameterHandler.ExperimentDb', return_value=self.store))
        self.enterContext(patch('ax3l.app.snakelab.RunSimulationHandler.ExperimentDb', return_value=self.store))
        self.db = Mock()
        self.decisions = ['learning_rate', 'run']
        self.prompts = []
        self.values = dict(hidden_size=96, layers=3, dropout=.02, sequence_length=12, batch_size=26,
                           learning_rate=.003, gamma=.97, epsilon_pair=(.91, .95),
                           reward_pair=(.25, -.5), epsilon_nice_pair=(.01, 40))

        async def select(llm, output, db, tools, prompts, *, parameter, process_id, decision_deadline):
            self.snake.submit_simulation.assert_not_called()
            self.prompts.append(prompts[-1].to_md())
            if parameter == REVISION_PARAMETER:
                step = self.decisions.pop(0)
                handler = RunSimulationHandler(db) if step == 'run' else SelectParameterHandler(db)
                payload = dict(draft_id=process_id)
                if step != 'run':
                    payload['parameter'] = step
                return handler.submit(payload)
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

    def trace(self):
        return [call.kwargs['parameter'] for call in self.conversation.await_args_list]

    def draft(self, count=0, phase='selecting_parameter', parameter=None):
        return ConfigurationDraft(str(uuid4()), self.gold,
                                  {'latest': self.latest, 'golden': self.gold, 'all_time_best': self.best},
                                  deepcopy(self.config), PARAMETER_ORDER[:count], phase, parameter=parameter)

    async def test_qwen_can_change_a_subset_out_of_order_and_revisit_the_same_setting(self):
        self.decisions = ['gamma', 'layers', 'gamma', 'run']
        await self.cycle()
        self.assertEqual(self.trace(), [REVISION_PARAMETER, 'gamma', REVISION_PARAMETER, 'layers',
                                       REVISION_PARAMETER, 'gamma', REVISION_PARAMETER])
        candidate = self.snake.submit_simulation.call_args.args[0]
        self.assertEqual(candidate['model']['layers'], 3)
        self.assertEqual(candidate['training']['gamma'], .97)
        self.assertEqual(candidate['training']['learning_rate'], self.config['training']['learning_rate'])
        self.assertEqual(candidate['epsilon_nice'], self.config['epsilon_nice'])
        self.assertEqual(set(self.store.saved.selections), {'gamma', 'layers'})
        self.assertEqual(len(self.store.saved.selections), 2)
        self.assertEqual(self.snake.is_config_unique.call_count, 3)
        self.snake.submit_simulation.assert_called_once()
        self.wait.assert_awaited_once_with(self.snake, self.db, self.run)
        self.assertEqual(self.store.saved.phase, 'completed')
        for call in self.conversation.await_args_list:
            prompt = call.args[4][0].to_md()
            self.assertIn('data_tool', prompt)
            self.assertIn('/draft', prompt)
            for run_id in (self.gold, self.latest, self.best):
                self.assertNotIn(run_id.split('-')[0], prompt)
        self.assertFalse(self.tools.call_args_list[0].kwargs['allow_run'])
        self.assertTrue(self.tools.call_args_list[-1].kwargs['allow_run'])

    async def test_one_change_can_run_without_choosing_the_other_nine_settings(self):
        await self.cycle()
        self.assertEqual(self.trace(), [REVISION_PARAMETER, 'learning_rate', REVISION_PARAMETER])
        self.assertEqual(self.store.saved.selections, ['learning_rate'])
        self.assertEqual(self.snake.is_config_unique.call_count, 1)
        self.snake.submit_simulation.assert_called_once()

    async def test_restart_resumes_the_explicit_setting_and_preserves_other_choices(self):
        self.store.saved = self.draft(3, 'choosing', parameter='gamma')
        self.store.saved.config['model'].update(hidden_size=104, layers=2, dropout=.03)
        self.decisions = ['run']
        await self.cycle()
        self.assertEqual(self.trace(), ['gamma', REVISION_PARAMETER])
        self.assertEqual(self.snake.submit_simulation.call_args.args[0]['model'], dict(
            type='transformer', heads=4, hidden_size=104, layers=2, dropout=.03))
        self.assertEqual(self.rotation.await_count, 1)

    async def test_duplicates_keep_the_parameter_and_reset_the_budget_only_after_unique_acceptance(self):
        self.snake.is_config_unique.side_effect = [False, False, True]
        self.decisions = ['layers', 'run']
        choose = self.conversation.side_effect

        async def revise(llm, output, db, tools, prompts, *, parameter, process_id, decision_deadline):
            if parameter != 'layers':
                return await choose(llm, output, db, tools, prompts, parameter=parameter,
                                    process_id=process_id, decision_deadline=decision_deadline)
            for value in (1, 2, 3):
                result = SubmitSingleValueHandler(db).submit(dict(draft_id=process_id, parameter='layers', value=value))
                if result['status'] == 'rejected':
                    self.assertEqual(self.store.saved.next_parameter, 'layers')
                    self.assertEqual(self.store.saved.config['model']['layers'], 1)
                    self.snake.submit_simulation.assert_not_called()
            return result

        self.conversation.side_effect = revise
        with patch('ax3l.app.snakelab.SnakeLabLoop.monotonic', side_effect=[100, 450]):
            await self.cycle()
        self.assertEqual(self.trace(), [REVISION_PARAMETER, 'layers', REVISION_PARAMETER])
        self.assertEqual([call.kwargs['decision_deadline'] for call in self.conversation.await_args_list],
                         [400, 400, 750])
        candidate = self.snake.submit_simulation.call_args.args[0]
        self.assertEqual(candidate['model']['hidden_size'], self.config['model']['hidden_size'])
        self.assertEqual(candidate['model']['layers'], 3)
        self.assertEqual(candidate['game']['rewards'], self.config['game']['rewards'])
        self.assertEqual(candidate['epsilon_nice'], self.config['epsilon_nice'])
        self.assertEqual(self.snake.is_config_unique.call_count, 3)
        self.assertEqual([call.kwargs['allow_run'] for call in self.tools.call_args_list],
                         [False, False, True])
        self.snake.submit_simulation.assert_called_once()

    async def test_restart_at_parameter_selection_can_choose_a_new_branch(self):
        self.store.saved = self.draft(1, 'selecting_parameter')
        self.store.saved.config['model']['hidden_size'] = 104
        self.decisions = ['dropout', 'run']
        await self.cycle()
        self.assertEqual(self.trace(), [REVISION_PARAMETER, 'dropout', REVISION_PARAMETER])
        candidate = self.snake.submit_simulation.call_args.args[0]
        self.assertEqual(candidate['model']['hidden_size'], 104)
        self.assertEqual(candidate['model']['dropout'], .02)

    async def test_restart_after_branch_selection_does_not_choose_the_branch_again(self):
        self.store.saved = self.draft(0, 'choosing', parameter='layers')
        self.decisions = ['run']
        await self.cycle()
        self.assertEqual(self.trace(), ['layers', REVISION_PARAMETER])
        self.assertEqual(self.snake.submit_simulation.call_args.args[0]['model']['layers'], 3)

    async def test_restart_with_a_unique_candidate_still_asks_qwen_whether_to_run(self):
        self.store.saved = self.draft(1, 'reviewing')
        self.decisions = ['run']
        await self.cycle()
        self.assertEqual(self.trace(), [REVISION_PARAMETER])
        self.assertIn('run_simulation', self.prompts[0])
        self.snake.is_config_unique.assert_not_called()
        self.snake.submit_simulation.assert_called_once()

    async def test_interrupted_reference_preparation_preserves_each_decision(self):
        for phase, parameter in (('selecting_parameter', None), ('reviewing', None), ('choosing', 'gamma')):
            with self.subTest(phase=phase):
                self.store.saved = self.draft(1, phase, parameter=parameter)
                original = deepcopy(self.store.saved)
                self.analysis.side_effect = asyncio.CancelledError()
                await self.cycle()
                self.assertEqual(self.store.saved, original)
        self.conversation.assert_not_awaited()
        self.snake.submit_simulation.assert_not_called()

    async def test_only_chosen_settings_get_their_relevant_chart(self):
        self.decisions = ['reward_pair', 'learning_rate', 'epsilon_pair', 'run']
        await self.cycle()
        messages = {call.kwargs['parameter']: json.loads(call.args[4][0].to_json())['content']
                    for call in self.conversation.await_args_list}
        for parameter in CHOICE_CHARTS:
            content = messages[parameter]
            self.assertEqual([part['type'] for part in content], ['text', 'image_url'])
            self.assertIn('The chart shows the latest run.', content[0]['text'])
        self.assertEqual([call.args[-1] for call in self.chart.call_args_list],
                         ['distribution', 'loss', 'scores'])
        data = json.loads(messages['epsilon_pair'][0]['text'].split('```json\n')[1].split('\n```')[0])
        self.assertEqual(data['reference_runs']['golden']['high_score'], 20)
        self.assertEqual(data['reference_runs']['latest']['mean_last_50_scores'], .2)
        self.assertEqual(data['current'], {key: self.config['epsilon'][key] for key in ('initial', 'decay')})
        self.assertNotIn('Previous notes.', messages['epsilon_pair'][0]['text'])

    async def test_golden_supplies_chart_after_seed_change_and_missing_loss_skips_chart(self):
        self.decisions = ['learning_rate', 'epsilon_pair', 'run']
        self.store.analyses[self.latest].config['seed'] += 1
        self.store.analyses[self.gold].metrics['episodes_with_loss'] = 0
        await self.cycle()
        messages = {call.kwargs['parameter']: json.loads(call.args[4][0].to_json())['content']
                    for call in self.conversation.await_args_list}
        self.assertIsInstance(messages['learning_rate'], str)
        self.assertIn('/golden/activity', messages['learning_rate'])
        self.assertIn('The chart shows the golden run.', messages['epsilon_pair'][0]['text'])
        self.assertEqual([call.args[-1] for call in self.chart.call_args_list], ['scores'])
        self.snake.get_analysis_episodes.assert_called_once_with(self.gold)

    async def test_reference_preparation_is_durable_and_resumes_before_choices(self):
        self.store.saved = self.draft(phase='preparing')
        original = deepcopy(self.store.saved)
        self.analysis.side_effect = asyncio.CancelledError()
        await self.cycle()
        self.assertEqual(self.store.saved, original)
        self.analysis.assert_called_once_with(self.snake, self.store, self.latest)
        self.conversation.assert_not_awaited()
        self.snake.submit_simulation.assert_not_called()
        self.snake.get_latest_completed_run_id.assert_not_called()

    async def test_restart_after_final_choice_does_not_repeat_any_conversation(self):
        self.store.saved = self.draft(len(PARAMETER_ORDER), 'ready')
        await self.cycle()
        self.conversation.assert_not_awaited()
        self.snake.submit_simulation.assert_called_once()

    async def test_restart_reconciles_a_lost_submission_reply_without_resubmitting(self):
        self.store.saved = self.draft(len(PARAMETER_ORDER), 'submitting')
        self.snake.find_config_run.return_value = self.run
        await self.cycle()
        self.snake.submit_simulation.assert_not_called()
        self.snake.find_config_run.assert_called_once_with(self.store.saved.config)
        self.wait.assert_awaited_once()
        self.conversation.assert_not_awaited()

    async def test_ambiguous_unrecorded_submission_stops_without_retry(self):
        self.store.saved = self.draft(len(PARAMETER_ORDER), 'submitting')
        self.snake.find_config_run.return_value = None
        with self.assertRaisesRegex(RuntimeError, 'will not be retried'):
            await optimize(Mock(), Path('/tmp'), self.db, 'endpoint')
        self.snake.submit_simulation.assert_not_called()
        self.wait.assert_not_awaited()

    async def test_submitted_run_is_not_submitted_again(self):
        self.store.saved = self.draft(len(PARAMETER_ORDER), 'submitted')
        self.store.saved.run_id = self.run
        await self.cycle()
        self.snake.submit_simulation.assert_not_called()
        self.wait.assert_awaited_once_with(self.snake, self.db, self.run)

    async def test_cancelled_simulation_is_marked_failed_without_comparison(self):
        self.store.saved = self.draft(len(PARAMETER_ORDER), 'submitted')
        self.store.saved.run_id = self.run
        self.wait.side_effect = SimulationUnsuccessful('cancelled')
        with self.assertRaises(SimulationUnsuccessful):
            await optimize(Mock(), Path('/tmp'), self.db, 'endpoint')
        self.assertEqual(self.store.saved.phase, 'failed')
        self.analysis.assert_not_called()
        self.assertNotIn('configuration_compared', [call.args[0] for call in self.db.log.call_args_list])

    async def test_one_reference_analysis_when_a_run_fills_all_three_roles(self):
        self.snake.get_latest_completed_run_id.return_value = self.gold
        self.snake.get_all_time_best_run_id.return_value = self.gold
        await self.cycle()
        self.assertEqual([call.args[2] for call in self.analysis.call_args_list], [self.gold, self.run])
        self.assertEqual(len(self.prompts), 3)

    async def test_recorded_comparison_resumes_analysis_without_comparing_again(self):
        self.store.saved = self.draft(len(PARAMETER_ORDER), 'submitted')
        self.store.saved.run_id = self.run
        self.store.comparisons[self.run] = {'current_golden_run_id': self.run,
                                           'reason': 'Improved', 'event_id': 123}
        self.events.current_golden_config.return_value = {'process_id': self.run}
        await self.cycle()
        self.assertNotIn('configuration_compared', [call.args[0] for call in self.db.log.call_args_list])
        self.analysis.assert_called_once()

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
        self.assertIn('baseline values from the golden configuration', prompt)
        self.assertIn('select_parameter', prompt)

    def test_ready_drafts_cannot_submit_epsilon_nice_values_above_either_cap(self):
        for probability, steps in ((.1, 41), (.11, 40)):
            with self.subTest(probability=probability, steps=steps):
                draft = self.draft(len(PARAMETER_ORDER), 'ready')
                draft.config['epsilon_nice'].update(probability=probability, steps=steps)
                original = deepcopy(draft)
                with self.assertRaises(ValidationError):
                    submit_draft(self.snake, self.db, self.store, draft)
                self.assertEqual(draft, original)
                self.assertIsNone(self.store.saved)
        self.snake.submit_simulation.assert_not_called()
        self.db.log.assert_not_called()

    def test_submission_intent_survives_transport_failure(self):
        draft = self.draft(len(PARAMETER_ORDER), 'ready')
        self.snake.submit_simulation.side_effect = TimeoutError('lost reply')
        with self.assertRaises(TimeoutError):
            submit_draft(self.snake, self.db, self.store, draft)
        self.assertEqual(self.store.saved.phase, 'submitting')
        self.snake.submit_simulation.assert_called_once()
