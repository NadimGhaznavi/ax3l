import io
from datetime import datetime
import unittest
from unittest.mock import Mock, patch

from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb
from ax3l.interface.SnakeLab import SnakeLab
from ax3l.server.ReportingServer import make_server


RUN_ID = "f6e72cb3-9bcf-4669-b368-a17c656bad79"


class SimulationControlTests(unittest.TestCase):
    def exchange(self, method, response, *args):
        with patch("ax3l.interface.SnakeLab.zmq.Context") as context:
            socket = context.return_value.__enter__.return_value.socket.return_value.__enter__.return_value
            socket.recv_json.side_effect = lambda: {
                "protocol_version": 1,
                "request_id": socket.send_json.call_args.args[0]["request_id"],
                "status": "ok", "payload": response,
            }
            result = getattr(SnakeLab(), method)(*args)
            return result, socket.send_json.call_args.args[0]

    def test_submit_and_status_request_contracts(self):
        config = {"seed": 1970}
        result, request = self.exchange("submit_simulation", {
            "run_id": RUN_ID, "state": "queued", "queue_position": 1,
        }, config)
        self.assertEqual(result, RUN_ID)
        self.assertEqual(request["method"], "simulation.submit")
        self.assertEqual(request["payload"], {"config": config})
        result, request = self.exchange("get_simulation_status", {
            "run_id": RUN_ID, "state": "running",
        }, RUN_ID)
        self.assertEqual(result, "running")
        self.assertEqual(request["method"], "simulation.status")
        self.assertEqual(request["payload"], {"run_id": RUN_ID})

    def test_mismatched_or_invalid_status_is_rejected(self):
        for payload in ({"run_id": "wrong", "state": "running"},
                        {"run_id": RUN_ID, "state": "idle"}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.exchange("get_simulation_status", payload, RUN_ID)

    def test_configuration_lookup_uses_dal_and_closes_connection(self):
        with patch("ax3l.interface.SnakeLab.DbMgr") as factory:
            db = factory.return_value
            db.query.return_value = [{"config": '{"seed":1970}'}]
            self.assertEqual(SnakeLab().get_config(RUN_ID), {"seed": 1970})
            factory.assert_called_once_with(env_prefix="SNAKELAB_DB", initialize_event_tables=False)
            db.query.assert_called_once_with(
                "SELECT config FROM simulation_runs WHERE run_id = %s", (RUN_ID,),
            )
            db.close.assert_called_once()
            db.query.side_effect = RuntimeError("unavailable")
            with self.assertRaises(RuntimeError):
                SnakeLab().get_config(RUN_ID)
            self.assertEqual(db.close.call_count, 2)
        db = Mock()
        db.query.return_value = []
        self.assertIsNone(SnakeLabDb(db).get_config(RUN_ID))


class ConfigPageTests(unittest.TestCase):
    def setUp(self):
        with patch("ax3l.server.ReportingServer.HTTPServer") as server:
            make_server("127.0.0.1", 0)
        self.handler_class = server.call_args.args[1]

    def request(self, path):
        handler = object.__new__(self.handler_class)
        handler.path = path
        handler.wfile = io.BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.send_error = Mock()
        handler.do_GET()
        return handler, handler.wfile.getvalue().decode()

    def test_detail_reads_current_config_each_time_and_escapes_values(self):
        with patch("ax3l.server.ReportingServer.SnakeLab.get_config") as get_config:
            get_config.side_effect = [
                {"seed": 1970, "text": "<script>bad</script>"}, {"seed": 1971}, None,
            ]
            handler, page = self.request(f"/simulations/{RUN_ID}/config")
            handler.send_response.assert_called_once_with(200)
            self.assertIn("1970", page)
            self.assertIn("&lt;script&gt;", page)
            self.assertNotIn("<script>", page)
            _, page = self.request(f"/simulations/{RUN_ID}/config")
            self.assertIn("1971", page)
            self.assertNotIn("1970", page)
            handler, _ = self.request(f"/simulations/{RUN_ID}/config")
            handler.send_error.assert_called_once_with(404, "Simulation not found")
            self.assertEqual(get_config.call_count, 3)
            get_config.assert_called_with(RUN_ID)

    def test_submission_message_links_config_by_run_id(self):
        event = dict(event_id=1, occurred_at=datetime.now(), name="simulation_submitted",
                     category="SnakeLab", log_level="INFO", content="Submitted config.",
                     process_id=RUN_ID)
        with patch("ax3l.server.ReportingServer.DbMgr"), patch(
            "ax3l.server.ReportingServer.EventLogDb"
        ) as log, patch("ax3l.server.ReportingServer.SnakeLab.is_simulation_running", return_value=True):
            log.return_value.recent.return_value = [event]
            _, page = self.request("/")
        self.assertIn(f'Submitted <a href="/simulations/{RUN_ID}/config">config</a>.', page)
