"""Retain streamed output before retries, protocol failures, and interruption."""

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from ax3l.constants.DEventCategory import DEventCategory as Events
from ax3l.entities.ExperimentView import VIEWS
from ax3l.interface.LLM import LLM, LLMTimeoutError
from ax3l.interface.LLMResponseCapture import LLMResponseCapture
from ax3l.interface.ViewConversation import ViewConversation
import test_llm
from view_cycle_fixtures import MemoryLog


class ResponseCaptureTests(unittest.TestCase):
    def test_one_event_is_updated_periodically_and_flushed_on_interruption(self):
        events = MemoryLog()
        response = dict(choices=[dict(message=dict(reasoning_content='First'))])
        with patch('ax3l.interface.LLMResponseCapture.monotonic', return_value=0) as clock:
            with self.assertRaises(KeyboardInterrupt):
                with LLMResponseCapture(events, 10, process_id='experiment', parent_event_id=1,
                                        source_name='selection', parameter='training') as capture:
                    self.assertEqual(json.loads(events.events[0]['content'])['capture']['received_chunks'], 0)
                    capture.receive(deepcopy(response))
                    self.assertEqual(json.loads(events.events[0]['content'])['choices'], response['choices'])
                    first_timestamp = json.loads(events.events[0]['content'])['capture']['last_chunk_at']
                    clock.return_value = 1
                    response['choices'][0]['message']['reasoning_content'] += ' second'
                    capture.receive(deepcopy(response))
                    self.assertNotIn('second', events.events[0]['content'])
                    clock.return_value = 6
                    capture.receive(deepcopy(response))
                    self.assertIn('second', events.events[0]['content'])
                    response['choices'][0]['message']['reasoning_content'] += ' last'
                    capture.receive(response)
                    raise KeyboardInterrupt()
        self.assertEqual(len(events.events), 1)
        event = events.events[0]
        self.assertEqual((event['name'], event['category']), (Events.LLM.RESPONSE_CAPTURED, Events.LLM.CATEGORY))
        self.assertEqual((event['parent_event_id'], event['process_id'], event['source_name'], event['parameter']),
                         (1, 'experiment', 'selection', 'training'))
        payload = json.loads(event['content'])
        self.assertEqual(payload['choices'], response['choices'])
        self.assertEqual(payload['capture']['status'], 'interrupted')
        self.assertEqual(payload['capture']['received_chunks'], 4)
        self.assertEqual(payload['capture']['request_event_id'], 10)
        self.assertGreaterEqual(payload['capture']['last_chunk_at'], first_timestamp)
        self.assertIn('KeyboardInterrupt', payload['capture']['error'])

    def test_incomplete_streams_never_execute_tools_and_capture_the_last_fragment(self):
        helper = test_llm.LLMTests()
        chunk = dict(choices=[dict(index=0, delta=dict(role='assistant', reasoning_content='Inspect the run.',
            tool_calls=[dict(index=0, id='call', type='function', function=dict(
                name='submit_observations', arguments='{"observations":"Good."}'))]))])
        for error in (TimeoutError('Stalled'), KeyboardInterrupt(), ConnectionResetError('Reset'), None):
            with self.subTest(error=error):
                events = MemoryLog()
                response = helper.stream_response(b'')
                lines = helper.frames(chunk, done=False).splitlines(keepends=True)
                response.readline.side_effect = [*lines, error if error is not None else b'']
                expected = type(error) if error is not None else ConnectionError
                if isinstance(error, TimeoutError):
                    expected = LLMTimeoutError
                with patch('ax3l.interface.LLM.urlopen', return_value=response):
                    with self.assertRaises(expected):
                        ViewConversation(LLM('http://local'), events).evaluate(VIEWS['training'], [], 'experiment')
                names = [event['name'] for event in events.events]
                self.assertNotIn(Events.Tool.STARTED, names)
                self.assertNotIn(Events.Conversation.RESPONSE, names)
                captures = [event for event in events.events if event['name'] == Events.LLM.RESPONSE_CAPTURED]
                self.assertEqual(len(captures), 1)
                payload = json.loads(captures[0]['content'])
                message = payload['choices'][0]['message']
                self.assertEqual(message['reasoning_content'], 'Inspect the run.')
                self.assertEqual(message['tool_calls'][0]['function']['arguments'], '{"observations":"Good."}')
                self.assertEqual(payload['capture']['status'], 'interrupted')
                self.assertEqual(events.events[-1]['name'], Events.Conversation.ENDED)
