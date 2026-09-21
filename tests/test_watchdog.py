"""Watchdog recovery decisions with isolated systemd and HTTP boundaries."""

import subprocess
import unittest
from unittest.mock import patch

from ax3l.activity.CheckServices import CheckServices
from ax3l.interface.Systemd import Systemd


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        systemd = patch('ax3l.activity.CheckServices.Systemd')
        health = patch('ax3l.activity.CheckServices.LLMHealth')
        clock = patch('ax3l.activity.CheckServices.time.monotonic', return_value=0)
        self.systemd = systemd.start().return_value
        self.health = health.start().return_value
        self.clock = clock.start()
        self.addCleanup(patch.stopall)
        self.systemd.state.return_value = 'active'
        self.health.status.return_value = {'healthy': True, 'http_status': 200}
        self.checker = CheckServices()

    def poll(self):
        self.checker.run('ax3l.service', 'phi.service', 'report.service', 'http://localhost/health')

    def test_healthy_services_are_left_running(self):
        self.clock.return_value = 60
        with self.assertNoLogs(level='DEBUG'):
            self.poll()
        self.health.status.assert_called_once_with('http://localhost/health')
        self.systemd.restart.assert_not_called()

    def test_inactive_and_failed_services_are_restarted(self):
        self.systemd.state.side_effect = ['failed', 'inactive', 'failed']
        with self.assertLogs(level='INFO') as logs:
            self.poll()
        self.assertTrue(any('Restarting phi.service' in line for line in logs.output))
        self.assertTrue(any('Restart requested for phi.service' in line for line in logs.output))
        self.assertEqual([call.args[0] for call in self.systemd.restart.call_args_list],
                         ['phi.service', 'ax3l.service', 'report.service'])
        self.health.status.assert_not_called()

    def test_health_failures_require_three_consecutive_polls(self):
        self.clock.return_value = 60
        self.health.status.return_value = {'healthy': False, 'http_status': 503}
        self.poll()
        self.poll()
        self.systemd.restart.assert_not_called()
        self.health.status.return_value = {'healthy': True}
        self.poll()
        self.health.status.return_value = {'healthy': False, 'error': 'timeout'}
        self.poll()
        self.poll()
        self.systemd.restart.assert_not_called()
        self.poll()
        self.systemd.restart.assert_called_once_with('phi.service')
        self.health.status.reset_mock()
        self.clock.return_value = 119
        self.poll()
        self.health.status.assert_not_called()
        self.clock.return_value = 120
        self.poll()
        self.health.status.assert_called_once()

    def test_startup_and_systemd_transitions_are_allowed_to_finish(self):
        self.poll()
        self.health.status.assert_not_called()
        self.clock.return_value = 60
        self.systemd.state.return_value = 'activating'
        self.poll()
        self.systemd.state.return_value = 'deactivating'
        self.poll()
        self.systemd.restart.assert_not_called()
        self.health.status.assert_not_called()

    def test_systemd_failure_does_not_stop_other_checks(self):
        self.systemd.state.side_effect = [subprocess.CalledProcessError(1, 'systemctl'), 'failed', 'inactive']
        self.systemd.restart.side_effect = [subprocess.TimeoutExpired('systemctl', 10), None]
        with self.assertLogs(level='ERROR'):
            self.poll()
        self.assertEqual(self.systemd.restart.call_count, 2)

    def test_restart_uses_nonblocking_systemd_job(self):
        with patch('ax3l.interface.Systemd.subprocess.run') as run:
            Systemd().restart('phi.service')
        run.assert_called_once_with(
            ['systemctl', '--no-block', 'restart', 'phi.service'],
            check=True, capture_output=True, text=True, timeout=10,
        )
