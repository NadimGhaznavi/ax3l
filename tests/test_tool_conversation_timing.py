"""Advisory countdowns follow elapsed time without blocking data or decisions."""

import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, Mock, patch

from ax3l.app.Prompt import Prompt
from ax3l.app.snakelab.ToolConversation import converse
from ax3l.app.snakelab.prompts.ConfigurationNextStep import ConfigurationNextStep
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


def reply(name, arguments):
    return 200, '', json.dumps({'choices': [{'message': dict(role='assistant', tool_calls=[
        dict(id=name, type='function', function=dict(name=name, arguments=json.dumps(arguments)))])}]}).encode()


class ToolConversationTimingTests(unittest.IsolatedAsyncioTestCase):
    def tools(self):
        definitions = [dict(function=dict(name=name, parameters=dict(properties={field: {}})))
                       for name, field in (('select_parameter', 'parameter'), ('data_tool', 'url'), ('kb_tool', 'url'))]
        return Mock(definition=definitions[0], definitions=definitions,
                    submit=AsyncMock(return_value=dict(status='ok', phase='choosing')),
                    reference=AsyncMock(return_value=dict(status='ok', page='Guide text.')),
                    data=AsyncMock())

    async def test_countdown_updates_after_every_data_request_and_allows_decisions_after_expiry(self):
        tools, db = self.tools(), Mock()
        page = json.dumps(dict(high_score=20))
        tools.data.side_effect = [dict(status='ok', page=page),
                                  dict(status='rejected', prompt=dict(role='user', content='Unknown data path.')),
                                  dict(status='ok', page=page)]
        llm = Mock(url='fixture')
        llm.complete.side_effect = [reply('kb_tool', dict(url='/')),
                                   reply('data_tool', dict(url='/golden/scores')),
                                   reply('data_tool', dict(url='/missing')),
                                   reply('data_tool', {}),
                                   reply('data_tool', dict(url='/draft')),
                                   reply('select_parameter', dict(parameter='gamma'))]
        with patch('ax3l.app.snakelab.ToolConversation.monotonic', side_effect=[100, 150.2, 240, 400, 450]):
            result = await converse(llm, Path('/tmp'), db, tools, [Prompt('Research a setting.')],
                                    parameter='revision', decision_deadline=400)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(tools.data.await_count, 3)
        tools.submit.assert_awaited_once_with(dict(parameter='gamma'))
        messages = json.loads(llm.complete.call_args.args[0])['messages']
        reminders = [message['content'] for message in messages
                     if message['role'] == 'user' and message['content'].startswith('Decision time remaining:')]
        self.assertEqual([text.split(' (')[0] for text in reminders], [
            'Decision time remaining: 05:00', 'Decision time remaining: 04:10',
            'Decision time remaining: 02:40', 'Decision time remaining: 00:00',
            'Decision time remaining: 00:00'])
        self.assertIn('advisory budget has elapsed', reminders[-1])
        self.assertEqual([message['content'] for message in messages if message['role'] == 'tool'],
                         ['Guide text.', page, 'Rejected.', 'Rejected.', page])
        logged = [json.loads(call.args[3])['content'] for call in db.log.call_args_list
                  if call.args[0] == 'prompt_sent' and call.kwargs['source_name'] == 'ToolConversation']
        self.assertTrue(all(reminder in logged for reminder in reminders))

    async def test_conversations_without_a_deadline_receive_no_timer_messages(self):
        tools, llm = self.tools(), Mock(url='fixture')
        tools.data.return_value = dict(status='ok', page='Data page.')
        llm.complete.side_effect = [reply('data_tool', dict(url='/')),
                                   reply('select_parameter', dict(parameter='gamma'))]
        with patch('ax3l.app.snakelab.ToolConversation.monotonic') as clock:
            await converse(llm, Path('/tmp'), Mock(), tools, [Prompt('Initial prompt.')])
        clock.assert_not_called()
        messages = json.loads(llm.complete.call_args.args[0])['messages']
        self.assertEqual([message['content'] for message in messages if message['role'] == 'user'],
                         ['Initial prompt.'])

    def test_next_step_prompts_explain_the_advisory_budget_and_unique_change_reset(self):
        draft = ConfigurationDraft('draft', 'gold', {}, SimulationConfiguration.defaults())
        for phase in ('selecting_parameter', 'reviewing'):
            draft.phase = phase
            text = ConfigurationNextStep(draft).to_md()
            self.assertIn('5 minutes', text)
            self.assertIn('advisory', text)
            self.assertIn('after each data_tool request', text)
            self.assertIn('accepted unique change starts a fresh', text)
