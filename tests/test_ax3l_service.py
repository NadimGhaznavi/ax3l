"""Exercise the listener and shutdown while the workflow is waiting."""

import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from ax3l.zmq.ZMQClient import ZMQClient
from ax3l.zmq.ZMQMsg import ZMQMsg


class Ax3lServiceTests(unittest.TestCase):
    def test_retired_actions_are_rejected_and_service_stops_cleanly(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'service.log'
            with output.open('w') as console:
                process = subprocess.Popen([
                    sys.executable, '-c',
                    'from unittest.mock import patch; '
                    'from threading import Event; '
                    'from ax3l.server.Ax3lServer import main; '
                    'patch("ax3l.server.Ax3lServer.DbMgr").start(); '
                    'patch("ax3l.server.Ax3lServer.ExperimentLoop.run", side_effect=lambda **kw: Event().wait()).start(); '
                    'raise SystemExit(main())',
                    '--zmq-endpoint', 'tcp://127.0.0.1:*',
                ], stdout=console, stderr=console,
                    env={key: value for key, value in os.environ.items() if not key.startswith('DB_')})
                try:
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        match = re.search(r'Ax3l listening on (tcp://[^;]+);', output.read_text())
                        if match:
                            break
                        self.assertIsNone(process.poll(), output.read_text())
                        time.sleep(.02)
                    else:
                        self.fail('Service did not start: ' + output.read_text())
                    client = ZMQClient(match[1], timeout=1)
                    for method in ('select_parameter', 'submit_single_value', 'submit_pair_values',
                                   'run_simulation', 'request_seed_change', 'submit_simulation_summary',
                                   'read_simulation_data', 'read_analysis_data'):
                        response = client.request(ZMQMsg('test', method, 'snakelab', {}))
                        self.assertEqual(response.payload['error']['code'], 'unknown_method')
                    process.send_signal(signal.SIGINT)
                    self.assertEqual(process.wait(timeout=5), 130, output.read_text())
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait()
