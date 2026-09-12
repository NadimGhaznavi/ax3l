import json
import unittest
from unittest.mock import Mock, patch

import zmq

from ax3l.zmq.ZMQClient import ZMQClient
from ax3l.zmq.ZMQMsg import ZMQMsg
from ax3l.zmq.ZMQServer import ZMQServer
from ax3l.server.ToolHandler import handle_tool


class ZMQServerTests(unittest.TestCase):
    def test_malformed_unknown_and_failed_requests_do_not_break_listener(self):
        handler = Mock(side_effect=[RuntimeError('backend failed'), {'status': 'ok'}])
        with patch('ax3l.zmq.ZMQServer.traceback.print_exc'), ZMQServer('tcp://127.0.0.1:*', handler) as server:
            client = ZMQClient(server.endpoint, timeout=1)
            bad = client.request_json({'not': 'an envelope'})
            self.assertEqual(bad['payload']['error']['code'], 'invalid_request')
            handler.assert_not_called()
            request = ZMQMsg('test', 'submit_single_value', 'snakelab', {})
            self.assertEqual(client.request(request).payload['error']['code'], 'handler_error')
            self.assertEqual(client.request(request).payload, {'status': 'ok'})
        self.assertFalse(server._thread.is_alive())

    def test_bind_error_is_reported_on_start(self):
        with ZMQServer('tcp://127.0.0.1:*', Mock()) as server:
            with self.assertRaises(zmq.ZMQError):
                with ZMQServer(server.endpoint, Mock()):
                    self.fail('Bind should fail')

    def test_dispatch_opens_and_closes_request_database(self):
        with patch('ax3l.server.ToolHandler.DbMgr') as db, patch('ax3l.server.ToolHandler.SubmitSingleValueHandler') as handler:
            request = ZMQMsg('test', 'submit_single_value', 'snakelab', {'parameter': 'learning_rate', 'value': 0.003})
            def submit(payload):
                db.return_value.log.assert_called_once_with(
                    'tool_request_received', 'Tool', 'INFO', json.dumps(request.to_dict(), ensure_ascii=False))
                return {'status': 'ok', 'run_id': 'run'}
            handler.return_value.submit.side_effect = submit
            self.assertEqual(handle_tool(request), {'status': 'ok', 'run_id': 'run'})
            handler.return_value.submit.assert_called_once_with(request.payload)
            db.return_value.close.assert_called_once()
            db.reset_mock()
            self.assertEqual(handle_tool(ZMQMsg('test', 'unknown', 'snakelab')).get('status'), 'error')
            db.assert_called_once()
            self.assertEqual(json.loads(db.return_value.log.call_args.args[3])['method'], 'unknown')
            db.return_value.close.assert_called_once()

    def test_log_failure_prevents_tool_execution(self):
        with patch('ax3l.server.ToolHandler.DbMgr') as db, patch('ax3l.server.ToolHandler.SubmitSingleValueHandler') as handler:
            db.return_value.log.side_effect = RuntimeError('Log unavailable')
            with self.assertRaisesRegex(RuntimeError, 'Log unavailable'):
                handle_tool(ZMQMsg('test', 'submit_single_value', 'snakelab', {}))
            handler.assert_not_called()
            db.return_value.close.assert_called_once()
