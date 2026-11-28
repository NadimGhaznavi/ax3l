"""Verify conversation restart orchestration without touching system services."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ResetConversationTests(unittest.TestCase):
    def run_script(self, *arguments, active=True, fail='', loaded=True, euid=0):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            calls = directory / 'calls'
            systemctl = directory / 'systemctl'
            systemctl.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$TEST_CALLS"
if [ "$1" = "$TEST_FAIL" ]; then exit 1; fi
case "$1" in
    show) echo "$TEST_LOAD_STATE";;
    is-active) exit "$TEST_INACTIVE";;
esac
''')
            systemctl.chmod(0o755)
            helper = directory / 'reset-conversation.sh'
            helper.write_text((ROOT / 'scripts/reset-conversation.sh').read_text().replace('$EUID', str(euid)))
            environment = dict(os.environ, PATH=f'{folder}:{os.environ["PATH"]}',
                               TEST_CALLS=str(calls), TEST_INACTIVE=str(int(not active)),
                               TEST_FAIL=fail, TEST_LOAD_STATE='loaded' if loaded else 'not-found')
            result = subprocess.run(['bash', str(helper), *arguments], env=environment,
                                    capture_output=True, text=True, timeout=10)
            return result, calls.read_text().splitlines() if calls.exists() else []

    def test_restarts_only_ax3l_and_restores_the_running_watchdog(self):
        result, calls = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [
            'show -p LoadState --value ax3l-server.service', 'is-active --quiet watchdog.service',
            'stop watchdog.service', 'restart ax3l-server.service', 'start watchdog.service',
        ])
        self.assertIn('rebuild its prompt and image', result.stdout)

    def test_keeps_an_inactive_watchdog_stopped(self):
        result, calls = self.run_script(active=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [
            'show -p LoadState --value ax3l-server.service', 'is-active --quiet watchdog.service',
            'restart ax3l-server.service',
        ])

    def test_failed_restart_restores_watchdog_and_reports_failure(self):
        result, calls = self.run_script(fail='restart')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls[-2:], ['restart ax3l-server.service', 'start watchdog.service'])
        self.assertNotIn('Ax3l restarted.', result.stdout)

    def test_failed_watchdog_stop_prevents_restart_and_restores_watchdog(self):
        result, calls = self.run_script(fail='stop')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls[-2:], ['stop watchdog.service', 'start watchdog.service'])
        self.assertNotIn('restart ax3l-server.service', calls)

    def test_failed_watchdog_restore_reports_failure(self):
        result, calls = self.run_script(fail='start')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls[-1], 'start watchdog.service')
        self.assertNotIn('Ax3l restarted.', result.stdout)

    def test_missing_installation_does_not_restart_services(self):
        result, calls = self.run_script(loaded=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, ['show -p LoadState --value ax3l-server.service'])

    def test_help_bad_arguments_and_non_root_calls_do_not_touch_services(self):
        for arguments, euid, status in ((('--help',), 1000, 0), (('--unknown',), 0, 2), ((), 1000, 1)):
            with self.subTest(arguments=arguments, euid=euid):
                result, calls = self.run_script(*arguments, euid=euid)
                self.assertEqual(result.returncode, status)
                self.assertEqual(calls, [])
