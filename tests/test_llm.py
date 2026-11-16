"""Inference requests use the default timeout or the remaining experiment budget."""

import unittest
from unittest.mock import MagicMock, patch

from ax3l.constants.DAx3l import DAx3l
from ax3l.interface.LLM import LLM


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
