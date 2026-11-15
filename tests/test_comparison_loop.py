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



    async def test_rejection_feedback_then_acceptance_in_same_conversation(self):
        llm = Mock(url='fixture')
        llm.complete.side_effect = [reply(.002), reply(.003)]
        db = Mock()
        tools = Mock(definition={'function': {'name': 'submit_single_value', 'parameters': {'properties': {'value': {}}}}})
        tools.definitions = [tools.definition]
        tools.submit = AsyncMock(side_effect=[{'status': 'rejected', 'source_name': 'NoDupes', 'prompt': {'role': 'user', 'content': 'Duplicate value'}}, {'status': 'ok', 'run_id': 'next'}])
        self.assertEqual(await converse(llm, Path('/tmp'), db, tools, [Prompt('initial')], parameter='learning_rate'), {'status': 'ok', 'run_id': 'next'})
        first, second = [json.loads(call.args[0]) for call in llm.complete.call_args_list]
        self.assertEqual(len(first['messages']), 1)
        self.assertEqual(second['messages'][2]['tool_call_id'], 'call-0.002')
        self.assertEqual(second['messages'][3]['content'], 'Duplicate value')
        names = [call.args[0] for call in db.log.call_args_list]
        self.assertEqual(names.count('conversation_started'), 1)
        self.assertEqual(names.count('prompt_sent'), 2)
        prompt_logs = [call for call in db.log.call_args_list if call.args[0] == 'prompt_sent']
        self.assertEqual([call.kwargs['source_name'] for call in prompt_logs], ['Prompt', 'NoDupes'])
        self.assertEqual([call.kwargs['parameter'] for call in prompt_logs], ['learning_rate'] * 2)
        self.assertTrue(all(call.kwargs.get('parameter') is None
                            for call in db.log.call_args_list if call.args[0] != 'prompt_sent'))
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
                tools.definitions = [tools.definition]
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
        tools.definitions = [tools.definition]
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




    async def test_monitor_logs_forgotten_run(self):
        snake, db = Mock(), Mock()
        snake.get_simulation_status.side_effect = SimulationUnavailable('forgotten')
        with self.assertRaises(SimulationUnavailable):
            await wait_for_run(snake, db, 'interrupted')
        self.assertEqual(db.log.call_args.args[0], 'simulation_failed')
        self.assertEqual(db.log.call_args.kwargs['process_id'], 'interrupted')
