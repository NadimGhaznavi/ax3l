"""Exercise the Snake Lab interface against a real local REP socket."""

from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

import zmq

from ax3l.interface.SnakeLab import SnakeLab


class SnakeLabTests(unittest.TestCase):
    def exchange(self, payload, **overrides):
        with zmq.Context() as context:
            with context.socket(zmq.REP) as server:
                server.setsockopt(zmq.LINGER, 0)
                server.setsockopt(zmq.RCVTIMEO, 2000)
                server.setsockopt(zmq.SNDTIMEO, 2000)
                port = server.bind_to_random_port("tcp://127.0.0.1")
                with ThreadPoolExecutor(max_workers=1) as pool:
                    result = pool.submit(
                        SnakeLab(f"tcp://127.0.0.1:{port}").is_simulation_running
                    )
                    request = server.recv_json()
                    self.assertEqual(set(request), {
                        "protocol_version", "request_id", "method", "payload"
                    })
                    self.assertEqual(request["protocol_version"], 1)
                    self.assertTrue(request["request_id"])
                    self.assertEqual(request["method"], "simulation.active")
                    self.assertEqual(request["payload"], {})
                    response = dict(request_id=request["request_id"],
                                    protocol_version=1, status="ok", payload=payload)
                    response.update(overrides)
                    server.send_json(response)
                    return result.result(timeout=2)

    def test_idle_and_busy_states(self):
        self.assertFalse(self.exchange({"run": None}))
        for state in ("running", "paused", "cancelling", "queued"):
            with self.subTest(state=state):
                self.assertTrue(self.exchange({"run": {"state": state}}))

    def test_invalid_payloads(self):
        for payload in (None, {}, {"run": False}, {"run": {}},
                        {"run": {"state": "completed"}}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.exchange(payload)

    def test_invalid_envelopes(self):
        for override in ({"protocol_version": True}, {"protocol_version": 2},
                         {"request_id": "wrong"}, {"status": "unknown"}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                self.exchange({"run": None}, **override)

    def test_server_error(self):
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            self.exchange(None, status="error", error={"code": "unavailable"})

    def test_timeout_then_success(self):
        with zmq.Context() as context:
            with context.socket(zmq.REP) as server:
                server.setsockopt(zmq.LINGER, 0)
                port = server.bind_to_random_port("tcp://127.0.0.1")
                with patch("ax3l.interface.SnakeLab.DSnakeLab.TIMEOUT_MS", 50):
                    with self.assertRaises(zmq.Again):
                        SnakeLab(f"tcp://127.0.0.1:{port}").is_simulation_running()
        self.assertFalse(self.exchange({"run": None}))
