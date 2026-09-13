import asyncio
import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from ax3l.app.Prompt import Prompt
from ax3l.app.snakelab.SnakeLabLoop import compare, optimize, wait_for_run, SimulationUnsuccessful
from ax3l.interface.SnakeLab import SimulationUnavailable
from ax3l.app.snakelab.ToolConversation import converse
from ax3l.app.snakelab.prompts.Comparison import Comparison
from ax3l.app.ideas.prompts.ComparisonPlot import ComparisonPlot
from ax3l.app.snakelab.prompts.ComparisonSingle import ComparisonSingle
from ax3l.activity.ReplyReport import reply_content

MODULE = 'ax3l.app.snakelab.SnakeLabLoop.'


def reply(value):
    return (200, '', json.dumps({'choices': [{'message': {'role': 'assistant', 'content': None,
        'tool_calls': [{'id': f'call-{value}', 'type': 'function', 'function': {
            'name': 'submit_single_value', 'arguments': json.dumps({'value': value})}}]}}]}).encode())


def result(score, lr):
    return {'status': 'completed', 'high_score': score, 'config': {'training': {'learning_rate': lr}}}


class ComparisonTests(unittest.TestCase):
    def test_wins_ties_and_losses(self):
        for score in (9, 10, 11):
            with self.subTest(score=score):
                snake, db = Mock(), Mock()
                snake.get_run_result.side_effect = [result(10, .002), result(score, .003)]
                snake.get_num_sims.return_value = 8
                self.assertEqual(compare(snake, db, 'gold', 'last'), 'last' if score > 10 else 'gold')
                logs = db.log.call_args_list
                self.assertEqual(logs[0].args[0], 'configuration_compared')
                self.assertEqual(logs[1].args[0], 'golden_config_created' if score > 10 else 'golden_config_retained')
                if score > 10:
                    self.assertEqual(logs[1].kwargs['experiment_score']['score'], score)
                    self.assertEqual(logs[1].kwargs['experiment_score']['simulations'], 8)
                else:
                    self.assertNotIn('experiment_score', logs[1].kwargs)
                self.assertIn(f'{score} {">" if score > 10 else "<="} 10', logs[1].args[3])

    def test_comparison_logs_the_actual_non_learning_rate_change(self):
        snake, db = Mock(), Mock()
        snake.get_run_result.side_effect = [
            {'status': 'completed', 'high_score': score, 'config': {'model': {'hidden_size': size}}}
            for score, size in [(10, 224), (12, 240)]]
        self.assertEqual(compare(snake, db, 'gold', 'last'), 'last')
        reason = json.loads(db.log.call_args_list[0].args[3])['reason']
        self.assertIn('model.hidden_size: 224 -> 240', reason)
        self.assertNotIn('learning_rate', reason)

    def test_missing_score_does_not_change_golden(self):
        snake, db = Mock(), Mock()
        snake.get_run_result.side_effect = [result(10, .002), result(None, .003)]
        with self.assertRaises(ValueError):
            compare(snake, db, 'gold', 'last')
        db.log.assert_not_called()

    def test_comparison_prompt_includes_parameter_history(self):
        latest = str(uuid4())
        rows = [{'learning_rate': .001, 'high_score': 4}, {'learning_rate': .003, 'high_score': 12}]
        with patch('ax3l.interface.SnakeLab.SnakeLab.get_run_result', return_value=result(12, .003)), patch('ax3l.interface.SnakeLab.SnakeLab.get_parameter_report', return_value=rows) as report:
            prompt = Comparison(latest, 'learning_rate')
        history = json.loads(prompt.to_md().split('```json\n')[1].split('```')[0])
        self.assertEqual(history, rows)
        report.assert_called_once_with(latest, 'learning_rate')
        for other in ('hidden_size', 'sequence_length', 'batch_size', 'gamma'):
            self.assertNotIn(other, prompt.to_md())
        self.assertIn('current golden', ComparisonSingle('learning_rate').to_md())

    def test_comparison_plot_builds_two_loss_curves_and_embeds_image(self):
        golden, latest = str(uuid4()), str(uuid4())
        figures = []
        # Exercise Plotly figure construction without requiring Kaleido PNG export.
        def render(figure, **kwargs):
            figures.append(figure)
            return b'png'
        with patch('ax3l.interface.SnakeLab.SnakeLab.get_episode_losses', side_effect=[[(1, None), (3, .2)], [(2, .5)]]), patch('plotly.graph_objects.Figure.to_image', render):
            plot = ComparisonPlot(golden, latest)
        figure = figures[0]
        self.assertEqual(len(figure.data), 2)
        self.assertEqual(list(figure.data[0].x), [1, 3])
        self.assertEqual(list(figure.data[0].y), [None, .2])
        self.assertEqual(list(figure.data[1].x), [2])
        self.assertEqual((figure.layout.width, figure.layout.height), (1500, 450))
        self.assertIn('data:image/png;base64,', plot.to_json())

    def test_tool_only_reply_is_readable(self):
        self.assertIn('submit_single_value(', reply_content(json.loads(reply(.003)[2])))


class LoopTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        selector = patch(MODULE + 'RoundRobinState')
        selector.start().return_value.begin.return_value = 'learning_rate'
        self.addCleanup(selector.stop)
        rotation = patch(MODULE + 'rotate_if_needed', new_callable=AsyncMock, return_value=None)
        rotation.start()
        self.addCleanup(rotation.stop)

    async def test_rejection_feedback_then_acceptance_in_same_conversation(self):
        llm = Mock(url='fixture')
        llm.complete.side_effect = [reply(.002), reply(.003)]
        db = Mock()
        tools = Mock(definition={'function': {'name': 'submit_single_value', 'parameters': {'properties': {'value': {}}}}})
        tools.submit = AsyncMock(side_effect=[{'status': 'rejected', 'source_name': 'NoDupes', 'prompt': {'role': 'user', 'content': 'Duplicate value'}}, {'status': 'ok', 'run_id': 'next'}])
        self.assertEqual(await converse(llm, Path('/tmp'), db, tools, [Prompt('initial')]), 'next')
        first, second = [json.loads(call.args[0]) for call in llm.complete.call_args_list]
        self.assertEqual(len(first['messages']), 1)
        self.assertEqual(second['messages'][2]['tool_call_id'], 'call-0.002')
        self.assertEqual(second['messages'][3]['content'], 'Duplicate value')
        names = [call.args[0] for call in db.log.call_args_list]
        self.assertEqual(names.count('conversation_started'), 1)
        self.assertEqual(names.count('prompt_sent'), 2)
        prompt_logs = [call for call in db.log.call_args_list if call.args[0] == 'prompt_sent']
        self.assertEqual([call.kwargs['source_name'] for call in prompt_logs], ['Prompt', 'NoDupes'])
        self.assertEqual(first['messages'], [{'role': 'user', 'content': 'initial'}])
        self.assertEqual(names.count('tool_execution_completed'), 2)
        self.assertEqual(names[-1], 'conversation_ended')

    async def test_missing_tool_call_stops_without_retry(self):
        for tool_fields in ({}, {'tool_calls': []}):
            with self.subTest(tool_fields=tool_fields):
                llm, db = Mock(url='fixture'), Mock()
                prose = {'role': 'assistant', 'content': 'Try increasing the learning rate.', **tool_fields}
                llm.complete.return_value = (200, '', json.dumps({'choices': [
                    {'message': prose, 'finish_reason': 'stop'}]}).encode())
                tools = Mock(definition={'function': {'name': 'submit_single_value', 'parameters': {'properties': {'value': {}}}}})
                tools.submit = AsyncMock()
                with self.assertRaisesRegex(ValueError, r"received \[\], finish_reason='stop'. See reply event"):
                    await converse(llm, Path('/tmp'), db, tools, [Prompt('initial')])
                llm.complete.assert_called_once()
                request = json.loads(llm.complete.call_args.args[0])
                self.assertEqual(request['tools'], [tools.definition])
                self.assertEqual(request['tool_choice'], 'required')
                self.assertFalse(request['parallel_tool_calls'])
                tools.submit.assert_not_awaited()
                logs = db.log.call_args_list
                self.assertEqual(sum(c.args[0] == 'prompt_sent' for c in logs), 1)
                self.assertEqual(sum(c.args[0] == 'reply_received' for c in logs), 1)
                self.assertEqual(logs[-1].args[0], 'conversation_ended')
                self.assertEqual(logs[-1].args[2], 'ERROR')
                self.assertIn('Expected exactly one submit_single_value tool call', logs[-1].args[3])

    async def test_ambiguous_tool_failure_stops_without_resubmission(self):
        llm, db = Mock(url='fixture'), Mock()
        llm.complete.return_value = reply(.003)
        tools = Mock(definition={'function': {'name': 'submit_single_value', 'parameters': {'properties': {'value': {}}}}})
        tools.submit = AsyncMock(side_effect=TimeoutError('timeout'))
        with self.assertRaises(TimeoutError):
            await converse(llm, Path('/tmp'), db, tools, [Prompt('initial')])
        self.assertEqual(llm.complete.call_count, 1)
        tools.submit.assert_awaited_once()
        self.assertIn('tool_execution_failed', [c.args[0] for c in db.log.call_args_list])

    async def test_monitor_logs_once_and_stops_failed_run(self):
        snake, db = Mock(), Mock()
        snake.get_simulation_status.side_effect = ['queued', 'running', 'running', 'failed']
        with patch(MODULE + 'asyncio.sleep', new_callable=AsyncMock), self.assertRaises(RuntimeError):
            await wait_for_run(snake, db, 'run')
        self.assertEqual([c.args[0] for c in db.log.call_args_list], ['simulation_started', 'simulation_failed'])

    async def exercise_loop(self, proposal=None, resume_error=None):
        snake = Mock()
        snake.is_simulation_running.return_value = False
        snake.get_run_result.return_value = result(10, .002)
        golden = Prompt('golden')
        golden.run_id = 'gold'
        context = AsyncMock()
        conversations = AsyncMock(side_effect=['last', 'next', asyncio.CancelledError()])
        with patch(MODULE + 'SnakeLab', return_value=snake), patch(MODULE + 'GoldenConfig', return_value=golden), patch(MODULE + 'SnakeLabTools', return_value=context), patch(MODULE + 'EventLogDb') as events, patch(MODULE + 'converse', conversations), patch(MODULE + 'wait_for_run', new_callable=AsyncMock) as wait, patch(MODULE + 'compare', side_effect=['last', 'last']) as comparison, patch(MODULE + 'Comparison', side_effect=lambda *ids: Prompt(str(ids))) as prompt:
            if resume_error is not None:
                wait.side_effect = [resume_error, None, None]
            events.return_value.latest_seed_baseline.return_value = None
            events.return_value.latest_snakelab_proposal.return_value = proposal
            with self.assertRaises(asyncio.CancelledError):
                await optimize(Mock(), Path('/tmp'), Mock(), 'endpoint')
            return conversations, comparison, prompt, wait

    async def test_restart_skips_interrupted_proposal_and_continues_with_golden(self):
        for error in (SimulationUnavailable('forgotten'), SimulationUnsuccessful('cancelled')):
            with self.subTest(error=error):
                conversations, comparison, prompt, wait = await self.exercise_loop(
                    {'process_id': 'interrupted', 'comparison': None}, error)
                self.assertEqual(wait.call_args_list[0].args[2], 'interrupted')
                self.assertEqual(comparison.call_args_list[0].args[2:], ('gold', 'last'))
                self.assertEqual(comparison.call_count, 2)
                self.assertEqual(prompt.call_args_list[0].args, ('gold', 'learning_rate'))
                self.assertEqual(len(conversations.call_args_list[0].args[4]), 2)

    async def test_restart_does_not_swallow_transport_failure(self):
        with self.assertRaises(TimeoutError):
            await self.exercise_loop({'process_id': 'pending', 'comparison': None}, TimeoutError())

    async def test_monitor_logs_forgotten_run(self):
        snake, db = Mock(), Mock()
        snake.get_simulation_status.side_effect = SimulationUnavailable('forgotten')
        with self.assertRaises(SimulationUnavailable):
            await wait_for_run(snake, db, 'interrupted')
        self.assertEqual(db.log.call_args.args[0], 'simulation_failed')
        self.assertEqual(db.log.call_args.kwargs['process_id'], 'interrupted')

    async def test_first_round_then_repeated_fresh_comparisons(self):
        conversations, comparison, prompt, wait = await self.exercise_loop()
        self.assertEqual([len(c.args[4]) for c in conversations.call_args_list], [3, 2, 2])
        self.assertEqual(comparison.call_args_list[0].args[2:], ('gold', 'last'))
        self.assertEqual(comparison.call_args_list[1].args[2:], ('last', 'next'))
        self.assertEqual(prompt.call_args_list[0].args, ('gold', 'learning_rate'))
        self.assertEqual(prompt.call_args_list[1].args, ('last', 'learning_rate'))
        for call in conversations.call_args_list:
            self.assertTrue(all(isinstance(json.loads(p.to_json())['content'], str) for p in call.args[4]))
            self.assertIn('learning_rate', call.args[4][-1].to_md())
            self.assertNotIn('hidden_size', call.args[4][-1].to_md())
        self.assertEqual(wait.await_count, 2)

    async def test_restart_uses_recorded_comparison_without_first_contact(self):
        snapshot = {'golden_run_id': 'old', 'latest_run_id': 'previous', 'current_golden_run_id': 'gold', 'reason': 'retained'}
        conversations, _, prompt, _ = await self.exercise_loop({'process_id': 'previous', 'comparison_id': 1, 'comparison': json.dumps(snapshot)})
        self.assertEqual(len(conversations.call_args_list[0].args[4]), 2)
        self.assertEqual(prompt.call_args_list[0].args, ('gold', 'learning_rate'))

    async def test_restart_monitors_pending_submission_before_requesting_next_value(self):
        snake, db = Mock(), Mock()
        snake.is_simulation_running.return_value = False
        snake.get_run_result.return_value = result(10, .002)
        golden = Prompt('golden')
        golden.run_id = 'gold'
        with patch(MODULE + 'SnakeLab', return_value=snake), patch(MODULE + 'GoldenConfig', return_value=golden), patch(MODULE + 'SnakeLabTools', return_value=AsyncMock()), patch(MODULE + 'EventLogDb') as events, patch(MODULE + 'converse', new_callable=AsyncMock) as conversation, patch(MODULE + 'wait_for_run', new_callable=AsyncMock) as wait, patch(MODULE + 'compare', return_value='pending') as comparison, patch(MODULE + 'Comparison', return_value=Prompt('comparison')), patch(MODULE + 'FirstContact') as first:
            events.return_value.latest_snakelab_proposal.return_value = {'process_id': 'pending', 'comparison': None}
            conversation.side_effect = asyncio.CancelledError()
            with self.assertRaises(asyncio.CancelledError):
                await optimize(Mock(), Path('/tmp'), db, 'endpoint')
            wait.assert_awaited_once_with(snake, db, 'pending')
            comparison.assert_called_once_with(snake, db, 'gold', 'pending')
            first.assert_not_called()
