"""Installer feedback keeps reporting activity and preserves command failures."""

from contextlib import redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    'install_progress', Path(__file__).resolve().parents[1] / 'scripts/install-progress.py')
progress = importlib.util.module_from_spec(spec)
spec.loader.exec_module(progress)


class InstallProgressTests(unittest.TestCase):
    def test_slow_command_reports_activity_and_completion(self):
        output = StringIO()
        with redirect_stdout(output):
            status = progress.run_step('Creating virtual environment',
                                       [sys.executable, '-c', 'import time; time.sleep(.1)'], interval=.01)
        self.assertEqual(status, 0)
        self.assertIn('Creating virtual environment...', output.getvalue())
        self.assertIn('still working', output.getvalue())
        self.assertIn('elapsed', output.getvalue())
        self.assertIn('complete', output.getvalue())

    def test_failure_preserves_exit_status_and_stops_activity_reporting(self):
        output = StringIO()
        with redirect_stdout(output):
            status = progress.run_step('Installing dependencies', [sys.executable, '-c', 'raise SystemExit(23)'])
        self.assertEqual(status, 23)
        self.assertIn('FAILED (exit 23)', output.getvalue())
        self.assertNotIn('complete', output.getvalue())

    def test_interrupt_finishes_progress_reporting(self):
        output = StringIO()
        with redirect_stdout(output), patch.object(progress.subprocess, 'run', side_effect=KeyboardInterrupt):
            self.assertEqual(progress.run_step('Creating environment', ['unused']), 130)
        self.assertIn('interrupted', output.getvalue())
        self.assertNotIn('complete', output.getvalue())
