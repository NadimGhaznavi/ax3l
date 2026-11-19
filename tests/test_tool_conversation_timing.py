"""Decision countdowns bound a conversation's decision budget and grace period."""

import asyncio
import json
from pathlib import Path
from threading import Event
from time import monotonic
import unittest
from unittest.mock import AsyncMock, Mock, patch

from ax3l.app.Prompt import Prompt
from ax3l.app.snakelab.ToolConversation import converse, DecisionTimeExpired, _time_reminder
from ax3l.app.snakelab.prompts.ConfigurationNextStep import ConfigurationNextStep
from ax3l.entities.ConfigurationDraft import ConfigurationDraft, PARAMETER_ORDER
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

    def test_unique_draft_reminders_show_the_three_minute_grace_period(self):
        with patch('ax3l.app.snakelab.ToolConversation.monotonic', side_effect=[250, 400, 450, 600]):
            reminders = [_time_reminder(400, 580)['content'] for _ in range(4)]
        self.assertIn('Decision time remaining: 02:30', reminders[0])
        self.assertIn('3-minute grace period', reminders[0])
        self.assertIn('Grace time remaining: 03:00', reminders[1])
        self.assertIn('Grace time remaining: 02:10', reminders[2])
        self.assertIn('Grace time remaining: 00:00', reminders[3])
        self.assertIn('continue the normal experiment cycle', reminders[3])

    def test_initial_reminders_explain_the_reset_without_offering_to_run_the_baseline(self):
        with patch('ax3l.app.snakelab.ToolConversation.monotonic', side_effect=[100, 400, 580]):
            reminders = [_time_reminder(400, 580, reset_on_expiry=True)['content'] for _ in range(3)]
        self.assertIn('Decision time remaining: 05:00', reminders[0])
        self.assertIn('3-minute grace period', reminders[0])
        self.assertIn('Grace time remaining: 03:00', reminders[1])
        self.assertIn('Grace time remaining: 00:00', reminders[2])
        for reminder in reminders:
            self.assertIn('restart from the initial prompt in a fresh conversation', reminder)
            self.assertNotIn('run the saved unique configuration', reminder)

    async def test_initial_expiry_logs_a_reset_and_ignores_a_late_inference_reply(self):
        tools, llm, db = self.tools(), Mock(url='fixture'), Mock()
        release = Event()

        def complete(payload, *, timeout_seconds):
            release.wait()
            return reply('select_parameter', dict(parameter='gamma'))

        llm.complete.side_effect = complete
        now = monotonic()
        try:
            with self.assertRaises(DecisionTimeExpired):
                await converse(llm, Path('/tmp'), db, tools, [Prompt('Research a setting.')],
                               decision_deadline=now - 180, conversation_deadline=now + .03,
                               reset_on_expiry=True)
        finally:
            release.set()
        tools.submit.assert_not_awaited()
        self.assertIn('restarting from the initial prompt', db.log.call_args.args[3])
        self.assertEqual(db.log.call_args.args[2], 'INFO')

    async def test_expired_grace_stops_before_requesting_or_submitting_another_choice(self):
        tools, llm, db = self.tools(), Mock(url='fixture'), Mock()
        with self.assertRaises(DecisionTimeExpired):
            await converse(llm, Path('/tmp'), db, tools, [Prompt('Decide.')],
                           decision_deadline=0, conversation_deadline=0)
        llm.complete.assert_not_called()
        tools.submit.assert_not_awaited()
        self.assertEqual(db.log.call_args.args[2], 'INFO')
        self.assertIn('grace period expired', db.log.call_args.args[3])

    async def test_expiry_discards_a_late_inference_reply_without_submitting_it(self):
        tools, llm = self.tools(), Mock(url='fixture')
        release = Event()

        def complete(payload, *, timeout_seconds):
            release.wait()
            return reply('select_parameter', dict(parameter='gamma'))

        llm.complete.side_effect = complete
        now = monotonic()
        try:
            with self.assertRaises(DecisionTimeExpired):
                await converse(llm, Path('/tmp'), Mock(), tools, [Prompt('Decide.')],
                               decision_deadline=now - 180, conversation_deadline=now + .03)
        finally:
            release.set()
        tools.submit.assert_not_awaited()

    async def test_expiry_can_interrupt_data_reads(self):
        tools, llm = self.tools(), Mock(url='fixture')
        llm.complete.return_value = reply('data_tool', dict(url='/draft'))

        async def read(arguments):
            await asyncio.Event().wait()

        tools.data.side_effect = read
        now = monotonic()
        with self.assertRaises(DecisionTimeExpired):
            await converse(llm, Path('/tmp'), Mock(), tools, [Prompt('Decide.')],
                           decision_deadline=now - 180, conversation_deadline=now + .03)
        tools.data.assert_awaited_once()
        tools.submit.assert_not_awaited()

    async def test_transport_timeouts_remain_failures_before_the_grace_deadline(self):
        tools, llm = self.tools(), Mock(url='fixture')
        llm.complete.side_effect = TimeoutError('transport failed')
        now = monotonic()
        with self.assertRaisesRegex(TimeoutError, 'transport failed'):
            await converse(llm, Path('/tmp'), Mock(), tools, [Prompt('Decide.')],
                           decision_deadline=now + 300, conversation_deadline=now + 480)
        tools.submit.assert_not_awaited()

    async def test_an_accepted_submission_finishes_without_cancellation_if_grace_expires_during_the_write(self):
        tools, llm = self.tools(), Mock(url='fixture')
        llm.complete.return_value = reply('select_parameter', dict(parameter='gamma'))
        current = [0]

        async def submit(arguments):
            current[0] = 600
            await asyncio.sleep(0)
            return dict(status='ok', phase='choosing')

        tools.submit.side_effect = submit
        with patch('ax3l.app.snakelab.ToolConversation.monotonic', side_effect=lambda: current[0]):
            result = await converse(llm, Path('/tmp'), Mock(), tools, [Prompt('Decide.')],
                                    decision_deadline=300, conversation_deadline=480)
        self.assertEqual(result['status'], 'ok')
        tools.submit.assert_awaited_once()

    def test_next_step_prompts_explain_the_budget_and_the_initial_reset_or_unique_submission(self):
        draft = ConfigurationDraft('draft', 'gold', {}, SimulationConfiguration.defaults())
        for phase, selections in (('selecting_parameter', []), ('reviewing', ['gamma'])):
            draft.phase = phase
            draft.selections = selections
            text = ConfigurationNextStep(draft, [name for name in PARAMETER_ORDER if name not in selections]).to_md()
            self.assertIn('5 minutes', text)
            self.assertIn('3 extra minutes', text)
            self.assertIn('After each data_tool request', text)
            self.assertIn('accepted unique change starts a fresh', text)
            self.assertIn('then Ax3l submits the saved unique configuration' if selections else
                          'then Ax3l restarts from the initial prompt in a fresh conversation', text)
            self.assertIn('Use data_tool at / for measured reference runs or /draft', text)
            self.assertNotIn('/golden/notes', text)

    def test_next_step_prompt_lists_only_unused_parameters_and_offers_run_when_all_are_used(self):
        draft = ConfigurationDraft('draft', 'gold', {}, SimulationConfiguration.defaults(),
                                    ['learning_rate', 'epsilon_pair'], 'reviewing')
        text = ConfigurationNextStep(draft, [name for name in PARAMETER_ORDER if name not in draft.selections]).to_md()
        choices = json.loads(text.split('```json\n')[1].split('\n```')[0])
        self.assertEqual(set(choices), set(PARAMETER_ORDER) - set(draft.selections))
        self.assertIn('only once per experiment', text)
        self.assertIn('keeping the current values is not allowed', text)
        draft.selections = PARAMETER_ORDER.copy()
        text = ConfigurationNextStep(draft, []).to_md()
        self.assertEqual(json.loads(text.split('```json\n')[1].split('\n```')[0]), {})
        self.assertIn('Use run_simulation to run it.', text)
