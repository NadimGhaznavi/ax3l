"""Inference requests preserve replies and distinguish timeouts from other failures."""

import unittest
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from ax3l.constants.DAx3l import DAx3l
from ax3l.interface.LLM import LLM, LLMTimeoutError


class LLMTests(unittest.TestCase):
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
