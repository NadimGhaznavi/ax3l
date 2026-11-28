"""Inference requests preserve replies and distinguish timeouts from other failures."""

import unittest
from copy import deepcopy
from email.message import Message
from io import BytesIO
import json
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from jsonschema import ValidationError

from ax3l.constants.DAx3l import DAx3l
from ax3l.interface.LLM import LLM, LLMTimeoutError


class LLMTests(unittest.TestCase):
    def stream_response(self, body):
        response = MagicMock(status=200)
        response.headers = Message()
        response.headers['Content-Type'] = 'text/event-stream; charset=utf-8'
        response.__enter__.return_value = response
        response.readline.side_effect = BytesIO(body).readline
        return response

    def frames(self, *chunks, done=True):
        return b''.join(b'data: ' + json.dumps(chunk, ensure_ascii=False).encode() + b'\n\n'
                        for chunk in chunks) + (b'data: [DONE]\n\n' if done else b'')

    def test_stream_assembles_reasoning_tools_usage_and_timings_before_socket_close(self):
        chunks = [
            dict(id='reply', object='chat.completion.chunk', model='local', choices=[dict(index=0, delta=dict(
                role='assistant', content=None, reasoning_content='Inspect 🌳 '))]),
            dict(choices=[dict(index=0, delta=dict(reasoning_content='results.', content='Ready.'))]),
            dict(choices=[dict(index=0, delta=dict(tool_calls=[dict(index=0, id='call', type='function',
                function=dict(name='submit_', arguments='{"observations":'))]))]),
            dict(choices=[dict(index=0, delta=dict(tool_calls=[dict(index=0,
                function=dict(name='observations', arguments='"Good."}'))]))]),
            dict(choices=[dict(index=0, delta={}, finish_reason='tool_calls')]),
            dict(choices=[], usage=dict(prompt_tokens=20, completion_tokens=10), timings=dict(predicted_ms=500)),
        ]
        # Comments, CRLF framing, and a multiline data event all occur on real SSE streams.
        body = b': keepalive\r\n\r\n' + self.frames(*chunks).replace(b'\n', b'\r\n', 2)
        body = body.replace(b'data: {"choices": [], "usage":', b'data: {"choices": [],\ndata: "usage":')
        response = self.stream_response(body)
        snapshots = []
        with patch('ax3l.interface.LLM.urlopen', return_value=response):
            status, _, reply = LLM('http://local').complete(b'Payload', on_progress=lambda value: snapshots.append(deepcopy(value)))
        self.assertEqual(status, 200)
        reply = json.loads(reply)
        message = reply['choices'][0]['message']
        self.assertEqual(message['reasoning_content'], 'Inspect 🌳 results.')
        self.assertEqual(message['content'], 'Ready.')
        self.assertEqual(message['tool_calls'], [dict(id='call', type='function', function=dict(
            name='submit_observations', arguments='{"observations":"Good."}'))])
        self.assertEqual(reply['choices'][0]['finish_reason'], 'tool_calls')
        self.assertEqual(reply['usage'], dict(prompt_tokens=20, completion_tokens=10))
        self.assertEqual(reply['timings'], dict(predicted_ms=500))
        self.assertEqual((reply['id'], reply['object'], reply['model']), ('reply', 'chat.completion', 'local'))
        self.assertEqual(len(snapshots), len(chunks))
        self.assertEqual(snapshots[0]['choices'][0]['message']['reasoning_content'], 'Inspect 🌳 ')
        response.read.assert_not_called()
        response.__exit__.assert_called_once()

    def test_stream_timeout_preserves_delivered_progress_and_closes_the_response(self):
        chunk = dict(choices=[dict(index=0, delta=dict(reasoning_content='Still thinking.'))])
        response = self.stream_response(b'')
        error = TimeoutError('Stalled stream')
        response.readline.side_effect = [*self.frames(chunk, done=False).splitlines(keepends=True), error]
        snapshots = []
        with patch('ax3l.interface.LLM.urlopen', return_value=response):
            with self.assertRaises(LLMTimeoutError) as caught:
                LLM('http://local').complete(b'Payload', on_progress=snapshots.append)
        self.assertIs(caught.exception.__cause__, error)
        self.assertEqual(snapshots[0]['choices'][0]['message']['reasoning_content'], 'Still thinking.')
        response.__exit__.assert_called_once()

    def test_incomplete_or_invalid_streams_fail_instead_of_accepting_partial_tools(self):
        valid = dict(choices=[dict(index=0, delta=dict(content='Partial'))])
        for body, exception in (
            (self.frames(valid, done=False), ConnectionError),
            (b'data: {broken}\n\n', ValueError),
            (self.frames(dict(choices=[dict(index=0, delta=dict(reasoning_content=7))])), ValidationError),
            (self.frames(dict(error=dict(message='Inference failed'))), RuntimeError),
        ):
            with self.subTest(body=body), patch('ax3l.interface.LLM.urlopen', return_value=self.stream_response(body)):
                with self.assertRaises(exception):
                    LLM('http://local').complete(b'Payload', on_progress=lambda value: None)

    def test_http_errors_keep_their_body_when_streaming_was_requested(self):
        response = self.stream_response(b'')
        response.status = 504
        response.read.return_value = b'Gateway timeout'
        progress = MagicMock()
        with patch('ax3l.interface.LLM.urlopen', return_value=response):
            self.assertEqual(LLM('http://local').complete(b'Payload', on_progress=progress)[::2],
                             (504, b'Gateway timeout'))
        progress.assert_not_called()

    def test_default_and_explicit_timeouts_preserve_the_response_contract(self):
        for arguments, timeout in (({}, DAx3l.HTTP_TIMEOUT_SECONDS), (dict(timeout_seconds=480), 480)):
            with self.subTest(arguments=arguments), patch('ax3l.interface.LLM.urlopen') as open_request:
                response = MagicMock(status=200, headers='Headers')
                response.__enter__.return_value = response
                response.read.return_value = b'Reply'
                open_request.return_value = response
                self.assertEqual(LLM('http://local').complete(b'Payload', **arguments), (200, 'Headers', b'Reply'))
                self.assertEqual(open_request.call_args.kwargs['timeout'], timeout)

    def test_connection_timeouts_preserve_their_cause(self):
        for error in (TimeoutError('Timed out'), URLError(TimeoutError('Timed out'))):
            with self.subTest(error=error), patch('ax3l.interface.LLM.urlopen', side_effect=error):
                with self.assertRaises(LLMTimeoutError) as caught:
                    LLM('http://local').complete(b'Payload')
                self.assertIs(caught.exception.__cause__, error)

    def test_response_body_timeout_closes_the_response(self):
        with patch('ax3l.interface.LLM.urlopen') as open_request:
            response = MagicMock()
            response.__enter__.return_value = response
            error = TimeoutError('Response body timed out')
            response.read.side_effect = error
            open_request.return_value = response
            with self.assertRaises(LLMTimeoutError) as caught:
                LLM('http://local').complete(b'Payload')
            self.assertIs(caught.exception.__cause__, error)
            response.__exit__.assert_called_once()

    def test_other_connection_errors_are_not_reclassified_as_timeouts(self):
        error = URLError(ConnectionRefusedError('Connection refused'))
        with patch('ax3l.interface.LLM.urlopen', side_effect=error):
            with self.assertRaises(URLError) as caught:
                LLM('http://local').complete(b'Payload')
            self.assertIs(caught.exception, error)
