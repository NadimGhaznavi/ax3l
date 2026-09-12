"""Exercise the service entry point with DEV MariaDB and a local LLM fixture."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
from threading import Thread
import time
import unittest
from urllib.request import urlopen


@unittest.skipUnless(os.environ.get("AX3L_TEST_DEV_DB") == "1", "requires DEV MariaDB")
class Ax3lServiceTests(unittest.TestCase):
    def test_health_and_graceful_stop_during_haiku_loop(self):
        self.assertEqual(os.environ["DB_NAME"], "ax3l_dev")
        from ax3l.app.DbMgr import DbMgr

        class LLMHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                body = b'{"choices":[{"message":{"content":"Test haiku"}}]}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        llm = HTTPServer(("127.0.0.1", 0), LLMHandler)
        worker = Thread(target=llm.serve_forever, daemon=True)
        worker.start()
        db = DbMgr()
        process_id = None
        try:
            with tempfile.TemporaryDirectory() as folder:
                output = Path(folder)
                with (output / "service.log").open("w+") as console:
                    process = subprocess.Popen([
                        sys.executable, "-m", "ax3l.server.Ax3lServer", "--port", "0",
                        "--llm-url", f"http://127.0.0.1:{llm.server_port}",
                        "--output", str(output / "haiku"),
                    ], stdout=console, stderr=console)
                    try:
                        deadline = time.monotonic() + 15
                        while time.monotonic() < deadline:
                            match = re.search(r"Conversation: ([\w-]+)", (output / "service.log").read_text())
                            if match:
                                process_id = match[1]
                                rows = db.query("SELECT name FROM events WHERE process_id = %s ORDER BY event_id", (process_id,))
                                if any(row["name"] == "wait_started" for row in rows):
                                    break
                            self.assertIsNone(process.poll(), (output / "service.log").read_text())
                            time.sleep(0.05)
                        else:
                            self.fail("Service did not reach its first wait")
                        self.assertFalse((output / "haiku").exists())
                        console.seek(0)
                        port = re.search(r"listening on 127.0.0.1:(\d+)", console.read()).group(1)
                        with urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as response:
                            self.assertEqual(json.load(response)["mode"], "haiku")
                        process.send_signal(signal.SIGINT)
                        self.assertEqual(process.wait(timeout=5), 130)
                        rows = db.query("SELECT name, log_level FROM events WHERE process_id = %s ORDER BY event_id", (process_id,))
                        self.assertEqual(rows[-1], {"name": "conversation_ended", "log_level": "INFO"})
                    finally:
                        if process.poll() is None:
                            process.kill()
                            process.wait()
        finally:
            if process_id:
                db.execute("DELETE FROM events WHERE process_id = %s ORDER BY event_id DESC", (process_id,))
            db.close()
            llm.shutdown()
            worker.join()
            llm.server_close()
