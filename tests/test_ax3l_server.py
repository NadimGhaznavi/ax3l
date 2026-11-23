"""Verify the idle entry point and its transport lifecycle."""

import unittest
from unittest.mock import patch

from ax3l.server.Ax3lServer import main


class Ax3lServerTests(unittest.TestCase):
    def run_server(self, *, error=None):
        with patch('sys.argv', ['ax3l', '--zmq-endpoint', 'tcp://127.0.0.1:*']), \
                patch('ax3l.server.Ax3lServer.DbMgr') as database, \
                patch('ax3l.server.Ax3lServer.ZMQServer') as transport, \
                patch('builtins.print'):
            server = transport.return_value.__enter__.return_value
            server.serve_forever.side_effect = error
            result = main()
            database.assert_called_once_with()
            database.return_value.close.assert_called_once_with()
            server.serve_forever.assert_called_once_with()
            transport.return_value.__exit__.assert_called_once()
            return result

    def test_listener_returns_normally_and_closes_transport(self):
        self.assertEqual(self.run_server(), 0)

    def test_interrupt_closes_transport_and_returns_service_stop_status(self):
        self.assertEqual(self.run_server(error=KeyboardInterrupt()), 130)

    def test_transport_failure_propagates(self):
        with self.assertRaisesRegex(RuntimeError, 'Listener failed'):
            self.run_server(error=RuntimeError('Listener failed'))

    def test_environment_endpoint_overrides_configuration(self):
        with patch.dict('os.environ', {'AX3L_ZMQ_ENDPOINT': 'tcp://127.0.0.2:61971'}), \
                patch('sys.argv', ['ax3l']), \
                patch('ax3l.server.Ax3lServer.DbMgr'), \
                patch('ax3l.server.Ax3lServer.ZMQServer') as transport, \
                patch('ax3l.server.Ax3lServer.Network.endpoint') as configured, \
                patch('builtins.print'):
            self.assertEqual(main(), 0)
            self.assertEqual(transport.call_args.args[0], 'tcp://127.0.0.2:61971')
            configured.assert_not_called()

    def test_database_initialization_failure_prevents_listener_start(self):
        with patch('sys.argv', ['ax3l', '--zmq-endpoint', 'tcp://127.0.0.1:*']), \
                patch('ax3l.server.Ax3lServer.DbMgr', side_effect=RuntimeError('Database unavailable')), \
                patch('ax3l.server.Ax3lServer.ZMQServer') as transport:
            with self.assertRaisesRegex(RuntimeError, 'Database unavailable'):
                main()
            transport.assert_not_called()
