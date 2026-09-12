import unittest
from unittest.mock import Mock, patch

import zmq

from ax3l.zmq.ZMQClient import ZMQClient
from ax3l.zmq.ZMQMsg import ZMQMsg


class ZMQClientTests(unittest.TestCase):
    def test_message_round_trip_and_envelope_validation(self):
        message = ZMQMsg('mcp-snakelab', 'submit_single_value', 'snakelab', {'parameter': 'learning_rate', 'value': 0.003})
        self.assertEqual(ZMQMsg.from_json(message.to_json()), message)
        for version in (2, True, '1'):
            with self.subTest(version=version), self.assertRaises(ValueError):
                ZMQMsg.from_dict({**message.to_dict(), 'protocol_version': version})
        with self.assertRaises(TypeError):
            ZMQMsg.from_dict({**message.to_dict(), 'payload': []})
        with self.assertRaises(ValueError):
            ZMQMsg('tool', 'submit', payload={'value': float('nan')}).to_json()

    def test_timeout_closes_socket_without_retry_and_next_call_uses_new_context(self):
        with patch('ax3l.zmq.ZMQClient.zmq.Context') as factory:
            context = factory.return_value.__enter__.return_value
            socket = context.socket.return_value.__enter__.return_value
            socket.recv_json.side_effect = [zmq.Again(), {'ok': True}]
            client = ZMQClient('tcp://127.0.0.1:12345', timeout=0.05)
            with self.assertRaises(zmq.Again):
                client.request_json({'value': 1})
            self.assertEqual(socket.send_json.call_count, 1)
            context.socket.return_value.__exit__.assert_called_once()
            factory.return_value.__exit__.assert_called_once()
            self.assertEqual(client.request_json({'value': 2}), {'ok': True})
            self.assertEqual(factory.call_count, 2)
            socket.setsockopt.assert_any_call(zmq.LINGER, 0)
            socket.setsockopt.assert_any_call(zmq.RCVTIMEO, 50)

    def test_invalid_timeout(self):
        for timeout in (0, -1, float('nan'), float('inf')):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                ZMQClient('tcp://127.0.0.1:12345', timeout)
