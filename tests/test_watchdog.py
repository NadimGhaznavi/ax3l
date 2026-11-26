"""Watchdog recovery is limited to Ax3l's application services."""

import subprocess
import unittest
from unittest.mock import patch

from ax3l.app.CheckServices import CheckServices
from ax3l.interface.Systemd import Systemd


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        systemd = patch('ax3l.app.CheckServices.Systemd')
        self.systemd = systemd.start().return_value
        self.addCleanup(systemd.stop)
        self.systemd.state.return_value = 'active'
        self.checker = CheckServices()

    def poll(self):
        self.checker.run('ax3l.service', 'report.service')

    def test_healthy_services_are_left_running(self):
        with self.assertNoLogs(level='DEBUG'):
            self.poll()
        self.assertEqual([call.args[0] for call in self.systemd.state.call_args_list],
                         ['ax3l.service', 'report.service'])
        self.systemd.restart.assert_not_called()

    def test_inactive_and_failed_services_are_restarted(self):
        self.systemd.state.side_effect = ['inactive', 'failed']
        with self.assertLogs(level='INFO') as logs:
            self.poll()
        self.assertTrue(any('Restarting ax3l.service' in line for line in logs.output))
        self.assertTrue(any('Restart requested for ax3l.service' in line for line in logs.output))
        self.assertEqual([call.args[0] for call in self.systemd.restart.call_args_list],
                         ['ax3l.service', 'report.service'])

    def test_systemd_transitions_are_allowed_to_finish(self):
        self.systemd.state.return_value = 'activating'
        self.poll()
        self.systemd.state.return_value = 'deactivating'
        self.poll()
        self.systemd.restart.assert_not_called()

    def test_systemd_failure_does_not_stop_other_checks(self):
        self.systemd.state.side_effect = [subprocess.CalledProcessError(1, 'systemctl'), 'failed']
        with self.assertLogs(level='ERROR'):
            self.poll()
        self.systemd.restart.assert_called_once_with('report.service')

    def test_failed_restart_does_not_stop_other_checks(self):
        self.systemd.state.side_effect = ['failed', 'inactive']
        self.systemd.restart.side_effect = [subprocess.TimeoutExpired('systemctl', 10), None]
        with self.assertLogs(level='ERROR'):
            self.poll()
        self.assertEqual(self.systemd.restart.call_count, 2)

    def test_restart_uses_nonblocking_systemd_job(self):
        with patch('ax3l.interface.Systemd.subprocess.run') as run:
            Systemd().restart('ax3l.service')
        run.assert_called_once_with(
            ['systemctl', '--no-block', 'restart', 'ax3l.service'],
            check=True, capture_output=True, text=True, timeout=10,
        )
