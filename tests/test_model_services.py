"""Validate model units and service switching without touching system services."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ModelServicesTests(unittest.TestCase):
    def test_units_validate_for_every_environment(self):
        for environment, suffix, port in [('dev', '-dev', 27768), ('qa', '-qa', 27769), ('prod', '', 27770)]:
            with self.subTest(environment=environment), tempfile.TemporaryDirectory() as folder:
                values = {
                    'ENV': environment, 'SUFFIX': suffix, 'USER': 'nobody',
                    'APP': str(ROOT), 'CONFIG': '/tmp/ax3l-test', 'LLM_PORT': str(port),
                    'AX3L_PORT': '27771', 'REPORT_PORT': '27772',
                    'QWEN_COMMAND': '/usr/bin/true --model /models/Qwen.gguf',
                    'PHI_COMMAND': '/usr/bin/true --model /models/Phi.gguf',
                }
                units = []
                for template in (ROOT / 'systemd').glob('*.service'):
                    content = template.read_text()
                    for key, value in values.items():
                        content = content.replace(f'@{key}@', value)
                    self.assertNotIn('@', content)
                    unit = Path(folder) / f'{template.stem}{suffix}.service'
                    unit.write_text(content)
                    units.append(str(unit))
                result = subprocess.run(['systemd-analyze', 'verify', *units], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                for model, other in [('qwen', 'phi'), ('phi', 'qwen')]:
                    content = (Path(folder) / f'{model}-server{suffix}.service').read_text()
                    self.assertIn(f'Conflicts={other}-server{suffix}.service', content)
                    self.assertIn(f'/models/{model.title()}.gguf', content)

    def run_helper(self, *arguments):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            log = directory / 'calls'
            commands = {
                'sudo': '#!/bin/sh\nexec "$@"\n',
                'systemctl': '#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_CALLS"\nif [ "$1" = show ]; then echo not-found; fi\n',
                'sleep': '#!/bin/sh\nprintf "sleep %s\\n" "$*" >> "$TEST_CALLS"\n',
            }
            for name, content in commands.items():
                script = directory / name
                script.write_text(content)
                script.chmod(0o755)
            env = dict(os.environ, PATH=f'{folder}:{os.environ["PATH"]}', TEST_CALLS=str(log), PYTHONDONTWRITEBYTECODE='1')
            result = subprocess.run(['bash', str(ROOT / 'scripts/services.sh'), '-env', 'dev', *arguments], env=env, capture_output=True, text=True)
            return result, log.read_text().splitlines() if log.exists() else []

    def test_selecting_each_model_stops_other_before_starting(self):
        for model, other in [('qwen', 'phi'), ('phi', 'qwen')]:
            with self.subTest(model=model):
                result, calls = self.run_helper('start', '-model', model)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls, [
                    f'disable --now {other}-server-dev.service',
                    f'enable {model}-server-dev.service',
                    f'start {model}-server-dev.service', 'sleep 7',
                    'start reporting-server-dev.service', 'start ax3l-server-dev.service',
                    'start watchdog-dev.service',
                ])

    def test_default_is_qwen(self):
        result, calls = self.run_helper('start')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('start qwen-server-dev.service', calls)

    def test_missing_units_do_not_break_stop_or_migration(self):
        result, calls = self.run_helper('stop')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 6)
        self.assertTrue(all(call.startswith('show -p LoadState --value ') for call in calls))
        self.assertIn('show -p LoadState --value llm-server-dev.service', calls)

    def test_invalid_selection_does_not_touch_services(self):
        result, calls = self.run_helper('start', '-model', 'invalid')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
