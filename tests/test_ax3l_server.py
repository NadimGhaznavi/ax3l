"""Verify service orchestration and cleanup around the four-view loop."""

import unittest
from unittest.mock import patch

from ax3l.server.Ax3lServer import main


class Ax3lServerTests(unittest.TestCase):
    def run_server(self, *, error=None):
        with patch('sys.argv', ['ax3l', '--zmq-endpoint', 'tcp://127.0.0.1:*',
                                '--llm-url', 'http://local:51001', '--cycles', '1']), \
                patch('ax3l.server.Ax3lServer.DbMgr') as database, \
                patch('ax3l.server.Ax3lServer.ZMQServer') as transport, \
                patch('ax3l.server.Ax3lServer.ExperimentLoop') as factory, \
                patch('ax3l.server.Ax3lServer.LLM') as llm, \
                patch('ax3l.server.Ax3lServer.SnakeLab') as snake, patch('builtins.print'):
            loop = factory.return_value
            loop.run.side_effect = error
            try:
                result = main()
            finally:
                database.assert_called_once_with()
                database.return_value.close.assert_called_once_with()
                transport.return_value.__exit__.assert_called_once()
            factory.assert_called_once_with(database.return_value, llm.return_value, snake.return_value)
            llm.assert_called_once_with('http://local:51001')
            loop.run.assert_called_once_with(cycles=1,
                check=transport.return_value.__enter__.return_value.check)
            return result

    def test_complete_cycle_closes_transport_and_database(self):
        self.assertEqual(self.run_server(), 0)

    def test_interrupt_closes_resources_and_returns_service_stop_status(self):
        self.assertEqual(self.run_server(error=KeyboardInterrupt()), 130)

    def test_workflow_failure_propagates_after_cleanup(self):
        with self.assertRaisesRegex(RuntimeError, 'Workflow failed'):
            self.run_server(error=RuntimeError('Workflow failed'))

    def test_environment_endpoint_and_configured_llm_are_used(self):
        with patch.dict('os.environ', {'AX3L_ZMQ_ENDPOINT': 'tcp://127.0.0.2:61971'}), \
                patch('sys.argv', ['ax3l']), patch('ax3l.server.Ax3lServer.DbMgr'), \
                patch('ax3l.server.Ax3lServer.ExperimentLoop') as workflow, \
                patch('ax3l.server.Ax3lServer.LLM') as llm, \
                patch('ax3l.server.Ax3lServer.Network.llamasrv_url', return_value='http://wintermute:51001'), \
                patch('ax3l.server.Ax3lServer.ZMQServer') as transport, \
                patch('ax3l.server.Ax3lServer.Network.endpoint') as configured, patch('builtins.print'):
            self.assertEqual(main(), 0)
            self.assertEqual(transport.call_args.args[0], 'tcp://127.0.0.2:61971')
            configured.assert_not_called()
            llm.assert_called_once_with('http://wintermute:51001')
            workflow.return_value.run.assert_called_once()

    def test_database_initialization_failure_prevents_listener_start(self):
        with patch('sys.argv', ['ax3l', '--zmq-endpoint', 'tcp://127.0.0.1:*']), \
                patch('ax3l.server.Ax3lServer.DbMgr', side_effect=RuntimeError('Database unavailable')), \
                patch('ax3l.server.Ax3lServer.ZMQServer') as transport:
            with self.assertRaisesRegex(RuntimeError, 'Database unavailable'):
                main()
            transport.assert_not_called()

    def test_invalid_cycle_limit_fails_before_database_access(self):
        for value in ('0', '-1', 'no'):
            with self.subTest(value=value), patch('sys.argv', ['ax3l', '--cycles', value]), \
                    patch('ax3l.server.Ax3lServer.DbMgr') as database, patch('sys.stderr'):
                with self.assertRaises(SystemExit) as error:
                    main()
                self.assertEqual(error.exception.code, 2)
                database.assert_not_called()
