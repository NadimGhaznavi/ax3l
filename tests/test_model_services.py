"""Validate model units and service switching without touching system services."""
import os
import shutil
import shlex
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ModelServicesTests(unittest.TestCase):
    def test_vision_command_and_missing_projector(self):
        from ax3l.constants.DQwenV import DQwenV

        installer = (ROOT / 'scripts/service-configuration.sh').read_text()
        production = installer.split('llm_paths=', 1)[1].split('\n}', 1)[0]
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            shutil.copytree(ROOT / 'ax3l/constants', directory / 'ax3l/constants')
            (directory / 'ax3l/constants/DLlama.py').write_text(
                f'class DLlama:\n    BASE_DIR = {folder!r}\n'
                f'    MODEL_DIR = {folder!r}\n    BIN_DIR = "bin"\n'
                '    SERVER = "llama-server"\n    HOST = "0.0.0.0"\n'
            )
            (directory / 'bin').mkdir()
            binary = directory / 'bin/llama-server'
            binary.write_text('#!/bin/sh\nexit 0\n')
            binary.chmod(0o755)
            (directory / DQwenV.GGUF).touch()
            projector = directory / DQwenV.MMPROJ
            projector.touch()
            command = (
                'set -euo pipefail\n'
                f'checkout_dir={shlex.quote(folder)}\n'
                f'config_dir={shlex.quote(folder)}\n'
                f'install_dir={shlex.quote(folder)}\n'
                'selected_model=qwenv\nllm_port=27770\nllm_host=0.0.0.0\nllm_paths='
                + production + '\nprintf "%s\\n" "$qwenv_command"\n'
            )
            result = subprocess.run(['bash', '-c', command], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(shlex.split(result.stdout), [
                str(binary), '--model', str(directory / DQwenV.GGUF),
                '--mmproj', str(projector), '-c', str(DQwenV.CONTEXT_SIZE), '--host', '0.0.0.0',
                '--port', '27770', '--metrics', '--jinja',
            ])
            projector.unlink()
            result = subprocess.run(['bash', '-c', command], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Install the vision projector', result.stderr)

    def test_units_validate(self):
        with tempfile.TemporaryDirectory() as folder:
            values = {
                'USER': 'nobody', 'MODEL': 'qwen',
                'APP': str(ROOT), 'CONFIG': '/tmp/ax3l-test', 'LLM_PORT': '27770',
                'REPORT_PORT': '28870', 'REPORT_HOST': '0.0.0.0',
                'LLM_URL': 'http://127.0.0.1:27770',
                'AX3L_ZMQ_ENDPOINT': 'tcp://127.0.0.1:61970',
                'AX3L_ARGS': '--llm-url http://127.0.0.1:27770 --output /var/lib/ax3l/snakelab',
                'QWEN_COMMAND': '/usr/bin/true --model /models/Qwen.gguf',
                'QWENV_COMMAND': '/usr/bin/true --model /models/Qwenv.gguf --mmproj /models/projector.gguf -c 4096',
                'PHI_COMMAND': '/usr/bin/true --model /models/Phi.gguf',
            }
            units = []
            for template in (ROOT / 'systemd').glob('*.service'):
                content = template.read_text()
                for key, value in values.items():
                    content = content.replace(f'@{key}@', value)
                self.assertNotIn('@', content)
                unit = Path(folder) / f'{template.stem}.service'
                unit.write_text(content)
                units.append(str(unit))
            result = subprocess.run(['systemd-analyze', 'verify', *units], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            app_unit = (Path(folder) / 'ax3l-server.service').read_text()
            self.assertIn('RuntimeDirectory=ax3l', app_unit)
            self.assertIn('Environment=XDG_CONFIG_HOME=/run/ax3l/chrome-config', app_unit)
            self.assertIn('Environment=XDG_CACHE_HOME=/run/ax3l/chrome-cache', app_unit)
            for model in ('qwen', 'phi', 'qwenv'):
                content = (Path(folder) / f'{model}-server.service').read_text()
                self.assertNotIn('Conflicts=', content)
                self.assertIn(f'/models/{model.title()}.gguf', content)

    def run_helper(self, *arguments):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            log = directory / 'calls'
            commands = {
                'systemctl': '#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_CALLS"\nif [ "$1" = show ]; then echo not-found; fi\n',
                'sleep': '#!/bin/sh\nprintf "sleep %s\\n" "$*" >> "$TEST_CALLS"\n',
            }
            for name, content in commands.items():
                script = directory / name
                script.write_text(content)
                script.chmod(0o755)
            env = dict(os.environ, PATH=f'{folder}:{os.environ["PATH"]}', TEST_CALLS=str(log), PYTHONDONTWRITEBYTECODE='1')
            helper = directory / 'services.sh'
            helper.write_text((ROOT / 'scripts/services.sh').read_text().replace('$EUID', '0')
                              .replace('cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."', f'cd -- {shlex.quote(str(ROOT))}'))
            result = subprocess.run(['bash', str(helper), *arguments], env=env, capture_output=True, text=True)
            return result, log.read_text().splitlines() if log.exists() else []

    def test_starting_each_model_leaves_other_models_alone(self):
        from ax3l.constants.DQwen import DQwen
        from ax3l.constants.DPhi import DPhi
        from ax3l.constants.DQwenV import DQwenV

        for model, constants in (('qwen', DQwen), ('phi', DPhi), ('qwenv', DQwenV)):
            with self.subTest(model=model):
                result, calls = self.run_helper('start', '-model', model)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls, [
                    f'enable {model}-server.service',
                    f'start {model}-server.service', f'sleep {constants.STARTUP_SECONDS}',
                    'start reporting-server.service', 'start ax3l-server.service',
                    'start watchdog.service',
                ])

    def test_default_is_qwen(self):
        result, calls = self.run_helper('start')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('start qwen-server.service', calls)

    def test_missing_units_do_not_break_stop_or_migration(self):
        result, calls = self.run_helper('stop')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 7)
        self.assertTrue(all(call.startswith('show -p LoadState --value ') for call in calls))
        self.assertIn('show -p LoadState --value llm-server.service', calls)

    def test_invalid_selection_does_not_touch_services(self):
        result, calls = self.run_helper('start', '-model', 'invalid')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
