"""Decision countdowns bound a conversation's decision budget and grace period."""

import asyncio
import json
from pathlib import Path
from threading import Event
from time import monotonic
import unittest
from unittest.mock import AsyncMock, Mock, patch

from ax3l.app.Prompt import Prompt
from ax3l.app.snakelab.ToolConversation import converse, DecisionTimeExpired
from ax3l.app.snakelab.prompts.ConfigurationNextStep import ConfigurationNextStep
from ax3l.entities.ConfigurationDraft import ConfigurationDraft, PARAMETER_ORDER
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


def reply(name, arguments):
    return 200, '', json.dumps({'choices': [{'message': dict(role='assistant', tool_calls=[
        dict(id=name, type='function', function=dict(name=name, arguments=json.dumps(arguments)))])}]}).encode()


class ToolConversationTimingTests(unittest.IsolatedAsyncioTestCase):
    def tools(self):
        definitions = [dict(function=dict(name=name, parameters=dict(properties={field: {}})))
                       for name, field in (('select_parameter', 'parameter'), ('kb_tool', 'url'))]
        return Mock(definition=definitions[0], definitions=definitions,
                    submit=AsyncMock(return_value=dict(status='ok', phase='choosing')),
                    read=AsyncMock())

    async def test_deadline_adds_no_timer_messages_during_research_or_rejections(self):
        tools, db = self.tools(), Mock()
        page = json.dumps(dict(high_score=20))
        tools.read.side_effect = [dict(status='ok', page='Guide text.'), dict(status='ok', page=page),
                                  dict(status='rejected', prompt=dict(role='user', content='Unknown data path.')),
                                  dict(status='ok', page=page)]
        llm = Mock(url='fixture')
        llm.complete.side_effect = [reply('kb_tool', dict(url='/')),
                                   reply('kb_tool', dict(url='/golden/scores')),
                                   reply('kb_tool', dict(url='/missing')),
                                   reply('kb_tool', {}),
                                   reply('kb_tool', dict(url='/draft')),
                                   reply('select_parameter', dict(parameter='gamma'))]
        result = await converse(llm, Path('/tmp'), db, tools, [Prompt('Research a setting.')],
                                parameter='revision', conversation_deadline=monotonic() + 300)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(tools.read.await_count, 4)
        tools.submit.assert_awaited_once_with(dict(parameter='gamma'))
        messages = json.loads(llm.complete.call_args.args[0])['messages']
        expected = ['Research a setting.', 'Unknown data path.',
                    'Call kb_tool with exactly these fields: url.']
        self.assertEqual([message['content'] for message in messages if message['role'] == 'user'], expected)
        self.assertEqual([message['content'] for message in messages if message['role'] == 'tool'],
                         ['Guide text.', page, 'Rejected.', 'Rejected.', page])
        logged = [json.loads(call.args[3])['content'] for call in db.log.call_args_list
                  if call.args[0] == 'prompt_sent']
        self.assertEqual(logged, expected)

    async def test_conversations_without_a_deadline_receive_no_timer_messages(self):
        tools, llm = self.tools(), Mock(url='fixture')
        tools.read.return_value = dict(status='ok', page='Data page.')
        llm.complete.side_effect = [reply('kb_tool', dict(url='/')),
                                   reply('select_parameter', dict(parameter='gamma'))]
        with patch('ax3l.app.snakelab.ToolConversation.monotonic') as clock:
            await converse(llm, Path('/tmp'), Mock(), tools, [Prompt('Initial prompt.')])
        clock.assert_not_called()
        messages = json.loads(llm.complete.call_args.args[0])['messages']
        self.assertEqual([message['content'] for message in messages if message['role'] == 'user'],
                         ['Initial prompt.'])

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
                               conversation_deadline=now + .03,
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
                           conversation_deadline=0)
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
                               conversation_deadline=now + .03)
        finally:
            release.set()
        tools.submit.assert_not_awaited()

    async def test_expiry_can_interrupt_data_reads(self):
        tools, llm = self.tools(), Mock(url='fixture')
        llm.complete.return_value = reply('kb_tool', dict(url='/draft'))

        async def read(arguments):
            await asyncio.Event().wait()

        tools.read.side_effect = read
        now = monotonic()
        with self.assertRaises(DecisionTimeExpired):
            await converse(llm, Path('/tmp'), Mock(), tools, [Prompt('Decide.')],
                           conversation_deadline=now + .03)
        tools.read.assert_awaited_once()
        tools.submit.assert_not_awaited()

    async def test_transport_timeouts_remain_failures_before_the_grace_deadline(self):
        tools, llm = self.tools(), Mock(url='fixture')
        llm.complete.side_effect = TimeoutError('transport failed')
        now = monotonic()
        with self.assertRaisesRegex(TimeoutError, 'transport failed'):
            await converse(llm, Path('/tmp'), Mock(), tools, [Prompt('Decide.')],
                           conversation_deadline=now + 480)
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
                                    conversation_deadline=480)
        self.assertEqual(result['status'], 'ok')
        tools.submit.assert_awaited_once()

    def test_next_step_prompts_explain_available_actions_without_mentioning_the_timer(self):
        draft = ConfigurationDraft('draft', 'gold', {}, SimulationConfiguration.defaults())
        for phase, selections in (('selecting_parameter', []), ('selecting_parameter', ['gamma']),
                                  ('reviewing', ['gamma'])):
            draft.phase = phase
            draft.selections = selections
            text = ConfigurationNextStep(draft, [name for name in PARAMETER_ORDER if name not in selections]).to_md()
            self.assertNotRegex(text.lower(), r'\b(timer|countdown|deadline|minutes?|seconds?|grace)\b')
            self.assertIn('Your role: Data Scientist', text)
            self.assertIn('Change configuration: call select_parameter', text)
            self.assertEqual('run_simulation' in text, phase == 'reviewing')
            self.assertIn('[Inspect current draft](/draft)', text)
            self.assertIn('Open menu URLs with kb_tool.', text)

    def test_next_step_prompt_lists_only_unused_parameters_and_offers_run_when_all_are_used(self):
        draft = ConfigurationDraft('draft', 'gold', {}, SimulationConfiguration.defaults(),
                                    ['learning_rate', 'epsilon_pair'], 'reviewing')
        text = ConfigurationNextStep(draft, [name for name in PARAMETER_ORDER if name not in draft.selections]).to_md()
        choices = json.loads(text.split('```json\n')[1].split('\n```')[0])
        self.assertEqual(set(choices), set(PARAMETER_ORDER) - set(draft.selections))
        self.assertIn('Change configuration: call select_parameter', text)
        self.assertIn('Run next simulation: call run_simulation', text)
        draft.selections = PARAMETER_ORDER.copy()
        text = ConfigurationNextStep(draft, []).to_md()
        self.assertEqual(json.loads(text.split('```json\n')[1].split('\n```')[0]), {})
        self.assertIn('Run next simulation: call run_simulation', text)
        self.assertNotIn('select_parameter', text)
