"""Health polling must not fill the dev/QA service journal."""

from contextlib import redirect_stderr, redirect_stdout
import io
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from ax3l.interface.HealthServer import HealthServer


class HealthServerTests(unittest.TestCase):
    def test_successful_poll_is_silent_but_http_errors_are_logged(self):
        output = io.StringIO()
        errors = io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            with HealthServer().make_server('llm-server', 0) as server:
                worker = Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    url = f'http://127.0.0.1:{server.server_port}'
                    with urlopen(url + '/health', timeout=3) as response:
                        self.assertEqual(response.status, 200)
                        response.read()
                    self.assertEqual(output.getvalue(), '')
                    self.assertEqual(errors.getvalue(), '')
                    with self.assertRaises(HTTPError) as raised:
                        urlopen(url + '/missing', timeout=3)
                    raised.exception.close()
                    self.assertIn('404', errors.getvalue())
                finally:
                    server.shutdown()
                    worker.join()
