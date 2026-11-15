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
from ax3l.app.snakelab.prompts.FirstContactEpsilonNicePair import FirstContactEpsilonNicePair
from ax3l.app.snakelab.prompts.FirstContactRewardPair import FirstContactRewardPair


class PairIntegrationTests(unittest.IsolatedAsyncioTestCase):

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
        tools.definitions = [tools.definition]
        self.assertEqual(await converse(llm, Path('/tmp'), db, tools, [Prompt('pair')],
                                        parameter='epsilon_pair'), {'status': 'ok', 'run_id': 'next'})
        prompt_logs = [call for call in db.log.call_args_list if call.args[0] == 'prompt_sent']
        self.assertEqual([call.kwargs['parameter'] for call in prompt_logs], ['epsilon_pair'] * 4)
        self.assertEqual([call.args[0] for call in tools.submit.await_args_list], [
            {'value_1': .91, 'value_2': .95}, {'value_1': .92, 'value_2': .96}])
        messages = json.loads(llm.complete.call_args.args[0])['messages']
        self.assertIn('submit_pair_values', messages[3]['content'])
