"""Exercise application service ordering without touching system services."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ServicesTests(unittest.TestCase):
    def run_helper(self, *arguments, state='loaded'):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            log = directory / 'calls'
            systemctl = directory / 'systemctl'
            systemctl.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_CALLS"\n'
                                 'if [ "$1" = show ]; then echo "$TEST_STATE"; fi\n')
            systemctl.chmod(0o755)
            env = dict(os.environ, PATH=f'{folder}:{os.environ["PATH"]}',
                       TEST_CALLS=str(log), TEST_STATE=state)
            helper = directory / 'services.sh'
            helper.write_text((ROOT / 'scripts/services.sh').read_text().replace('$EUID', '0'))
            result = subprocess.run(['bash', str(helper), *arguments], env=env, capture_output=True, text=True)
            return result, log.read_text().splitlines() if log.exists() else []

    def test_start_only_starts_application_services_in_order(self):
        result, calls = self.run_helper('start')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ['start reporting-server.service', 'start ax3l-server.service',
                                 'start watchdog.service'])

    def test_stop_only_stops_application_services_in_reverse_order(self):
        result, calls = self.run_helper('stop')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [
            'show -p LoadState --value watchdog.service', 'stop watchdog.service',
            'show -p LoadState --value ax3l-server.service', 'stop ax3l-server.service',
            'show -p LoadState --value reporting-server.service', 'stop reporting-server.service',
        ])

    def test_stop_skips_missing_application_units(self):
        result, calls = self.run_helper('stop', state='not-found')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(call.startswith('show -p LoadState --value ') for call in calls))

    def test_invalid_or_retired_arguments_do_not_touch_services(self):
        for arguments in ((), ('restart',), ('start', '-model', 'qwen'), ('stop', 'extra')):
            with self.subTest(arguments=arguments):
                result, calls = self.run_helper(*arguments)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(calls, [])
