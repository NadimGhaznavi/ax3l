import asyncio
import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, Mock, patch

from ax3l.app.Prompt import Prompt
from ax3l.app.snakelab.RoundRobinState import ROUND_ROBIN_ORDER
from ax3l.app.snakelab.SnakeLabLoop import optimize
from ax3l.app.snakelab.ToolConversation import converse
from ax3l.app.snakelab.prompts.FirstContactEpsilonPair import FirstContactEpsilonPair
from ax3l.app.snakelab.prompts.FirstContactRewardPair import FirstContactRewardPair


class PairIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_cycle_selects_pair_reports_prompts_and_bound_tools(self):
        module = 'ax3l.app.snakelab.SnakeLabLoop.'
        snake = Mock()
        snake.parameter_space_exhausted.return_value = False
        snake.is_simulation_running.return_value = False
        snake.get_run_result.return_value = {'status': 'completed', 'high_score': 37}
        golden = Mock(run_id='gold')
        events = Mock()
        events.latest_snakelab_proposal.return_value = None
        events.latest_seed_baseline.return_value = None
        with patch(module + 'SnakeLab', return_value=snake), patch(module + 'GoldenConfig', return_value=golden), patch(module + 'EventLogDb', return_value=events), patch(module + 'rotate_if_needed', new_callable=AsyncMock, return_value=None), patch(module + 'RoundRobinState') as selector, patch(module + 'SnakeLabTools', return_value=AsyncMock()) as tools, patch(module + 'converse', new_callable=AsyncMock) as conversation, patch(module + 'wait_for_run', new_callable=AsyncMock) as wait, patch(module + 'compare', return_value='gold'), patch(module + 'Comparison', return_value=Prompt('single')), patch(module + 'ComparisonEpsilonPair', return_value=Prompt('epsilon report')) as epsilon, patch(module + 'ComparisonRewardPair', return_value=Prompt('reward grid')) as reward:
            selector.return_value.begin.side_effect = ROUND_ROBIN_ORDER + ROUND_ROBIN_ORDER[:1]
            conversation.side_effect = [f'run-{i}' for i in range(7)] + [asyncio.CancelledError()]
            with self.assertRaises(asyncio.CancelledError):
                await optimize(Mock(), Path('/tmp'), Mock(), 'endpoint')
            self.assertEqual([call.args[1] for call in tools.call_args_list], ROUND_ROBIN_ORDER + ROUND_ROBIN_ORDER[:1])
            self.assertEqual([call.kwargs['parameter'] for call in conversation.call_args_list],
                             ROUND_ROBIN_ORDER + ROUND_ROBIN_ORDER[:1])
            epsilon.assert_called_once_with('gold')
            reward.assert_called_once_with('gold')
            epsilon_prompts = conversation.call_args_list[5].args[4]
            reward_prompts = conversation.call_args_list[6].args[4]
            self.assertEqual(epsilon_prompts[1].to_md(), 'epsilon report')
            self.assertIsInstance(epsilon_prompts[2], FirstContactEpsilonPair)
            self.assertEqual(reward_prompts[1].to_md(), 'reward grid')
            self.assertIsInstance(reward_prompts[2], FirstContactRewardPair)
            self.assertEqual(wait.await_count, 7)

    async def test_pair_arguments_cannot_override_assignment_and_rejections_retry(self):
        def reply(arguments):
            return 200, '', json.dumps({'choices': [{'message': {
                'role': 'assistant', 'tool_calls': [{'id': 'pair-call', 'type': 'function',
                'function': {'name': 'submit_pair_values', 'arguments': json.dumps(arguments)}}]}}]}).encode()
        llm = Mock(url='fixture')
        llm.complete.side_effect = [reply({'pair': 'reward_pair', 'value_1': .91, 'value_2': .95}),
                                    reply({'value_1': .91}), reply({'value_1': .91, 'value_2': .95}),
                                    reply({'value_1': .92, 'value_2': .96})]
        tools = Mock(definition={'function': {'name': 'submit_pair_values', 'parameters': {
            'properties': {'value_1': {}, 'value_2': {}}}}}, submit=AsyncMock(side_effect=[
                {'status': 'rejected', 'prompt': {'role': 'user', 'content': 'Duplicate pair'}},
                {'status': 'ok', 'run_id': 'next'}]))
        db = Mock()
        self.assertEqual(await converse(llm, Path('/tmp'), db, tools, [Prompt('pair')],
                                        parameter='epsilon_pair'), 'next')
        prompt_logs = [call for call in db.log.call_args_list if call.args[0] == 'prompt_sent']
        self.assertEqual([call.kwargs['parameter'] for call in prompt_logs], ['epsilon_pair'] * 4)
        self.assertEqual([call.args[0] for call in tools.submit.await_args_list], [
            {'value_1': .91, 'value_2': .95}, {'value_1': .92, 'value_2': .96}])
        messages = json.loads(llm.complete.call_args.args[0])['messages']
        self.assertIn('submit_pair_values', messages[3]['content'])
