"""HTTP integration check using the disposable DEV event database."""

import os
import json
from threading import Thread
import unittest
from urllib.request import urlopen
from urllib.error import HTTPError
from uuid import uuid4


@unittest.skipUnless(os.environ.get("AX3L_TEST_DEV_DB") == "1", "requires DEV MariaDB")
class ReportingTests(unittest.TestCase):
    def test_log_page_refresh_and_escaping(self):
        self.assertEqual(os.environ["DB_NAME"], "ax3l_dev")
        from ax3l.app.DbMgr import DbMgr
        from ax3l.server.ReportingServer import make_server

        db = DbMgr()
        process_id = str(uuid4())
        self.addCleanup(db.close)
        self.addCleanup(db.execute, "DELETE FROM events WHERE process_id = %s", (process_id,))
        first = f"{process_id} <script>alert('test')</script>\nNext line"
        db.log("report_test", "System", "INFO", first, process_id=process_id)
        server = make_server("127.0.0.1", 0)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}"
            with urlopen(url) as response:
                page = response.read().decode()
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                self.assertIn("Refresh</button>", page)
                self.assertIn("&lt;script&gt;", page)
                self.assertNotIn("<script>", page)
                self.assertIn("Next line", page)
            second = f"{process_id} refreshed event"
            db.log("report_test", "System", "INFO", second, process_id=process_id)
            with urlopen(url) as response:
                page = response.read().decode()
                self.assertLess(page.index(second), page.index("&lt;script&gt;"))
            with urlopen(url + "/health") as response:
                self.assertEqual(response.status, 200)

            reply_text = "Quiet <script>night</script>\nA tree's shade"
            payload = {
                "choices": [{"index": 0, "finish_reason": "stop", "message": {
                    "role": "assistant", "content": reply_text,
                }}],
                "model": "Qwen2.5-VL", "id": "chatcmpl-test",
                "usage": {"prompt_tokens": 24, "prompt_tokens_details": {"cached_tokens": 0}},
                "timings": {"predicted_ms": 946.36},
                "extra": {"flag": False, "empty": [], "missing": None},
            }
            event_id = db.log("reply_received", "Conversation", "INFO", json.dumps(payload), process_id=process_id)
            with urlopen(url) as response:
                page = response.read().decode()
                self.assertIn(f'href="/events/{event_id}">Quiet &lt;script&gt;night&lt;/script&gt;', page)
                self.assertNotIn("chatcmpl-test", page)
            with urlopen(f"{url}/events/{event_id}") as response:
                page = response.read().decode()
                self.assertIn("Quiet &lt;script&gt;night&lt;/script&gt;", page)
                self.assertNotIn("<script>", page)
                for value in ("usage.prompt_tokens_details.cached_tokens", "timings.predicted_ms", "946.36", "chatcmpl-test", "choices[0].finish_reason", "extra.flag", "false", "extra.empty", "[]", "null"):
                    self.assertIn(value, page)
            with self.assertRaises(HTTPError) as error:
                urlopen(url + "/events/0")
            self.assertEqual(error.exception.code, 404)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
