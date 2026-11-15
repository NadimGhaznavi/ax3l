"""Verify entry-point lifecycle without an HTTP listener or external services."""

import unittest
from unittest.mock import MagicMock, patch

from ax3l.server.Ax3lServer import main


class Ax3lServerTests(unittest.TestCase):
    def test_optimization_returns_loop_status_and_closes_transport(self):
        loop = MagicMock()
        loop.main.return_value = 130
        with patch('sys.argv', ['ax3l', '--llm-url', 'http://localhost:51001',
                                '--zmq-endpoint', 'tcp://127.0.0.1:*']), \
                patch('ax3l.server.Ax3lServer.ZMQServer') as transport, \
                patch('ax3l.server.Ax3lServer.import_module', return_value=loop):
            transport.return_value.__enter__.return_value.endpoint = 'tcp://127.0.0.1:12345'
            self.assertEqual(main(), 130)
            loop.main.assert_called_once_with([
                '--url', 'http://localhost:51001', '--output', 'tmp/snakelab',
                '--zmq-endpoint', 'tcp://127.0.0.1:12345',
            ])
            transport.return_value.__exit__.assert_called_once_with(None, None, None)

    def test_default_runs_optimization_against_llamasrv(self):
        loop = MagicMock()
        loop.main.return_value = 0
        with patch('sys.argv', ['ax3l']), \
                patch('ax3l.server.Ax3lServer.ZMQServer') as transport, \
                patch('ax3l.server.Ax3lServer.Network.llamasrv_url', return_value='http://127.0.0.1:51001'), \
                patch('ax3l.server.Ax3lServer.import_module', return_value=loop):
            transport.return_value.__enter__.return_value.endpoint = 'tcp://127.0.0.1:61970'
            self.assertEqual(main(), 0)
            self.assertEqual(loop.main.call_args.args[0][:2], ['--url', 'http://127.0.0.1:51001'])
            transport.return_value.__exit__.assert_called_once_with(None, None, None)
