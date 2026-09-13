"""Run installer orchestration in a disposable checkout with host actions stubbed.

Only absolute host paths and EUID checks are redirected in the fixture script.
Rendering, MCP generation, file copying, chmod, and systemd validation are real.
Package/browser provisioning, ownership changes, and systemctl are simulated.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallServicesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ax3l-installer-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('scripts', 'systemd', 'ax3l'):
            shutil.copytree(ROOT / name, self.root / name,
                            ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy(ROOT / 'requirements.txt', self.root)
        self.units = self.root / 'units'
        self.units.mkdir()
        self.log = self.root / 'calls'
        self.bin = self.root / 'test-bin'
        self.bin.mkdir()
        script = self.root / 'scripts/install-services.sh'
        script.write_text(script.read_text().replace('$EUID', '$TEST_EUID')
                          .replace('/opt/$install_env/ax3l', str(self.root / '$install_env/ax3l'))
                          .replace('config_dir=/etc/ax3l', f'config_dir={self.root}/etc/ax3l')
                          .replace('/etc/systemd/system', str(self.units)))
        helper = self.root / 'scripts/services.sh'
        helper.write_text(helper.read_text().replace('$EUID', '$TEST_EUID'))
        constants = self.root / 'ax3l/constants/DLlama.py'
        constants.write_text(constants.read_text().replace('/opt/prod/', str(self.root) + '/'))
        self.executable(self.root / 'llama.cpp/bin/llama-server', '#!/bin/sh\nexit 0\n')
        from ax3l.constants.DQwen import DQwen
        from ax3l.constants.DPhi import DPhi
        from ax3l.constants.DQwenV import DQwenV
        self.models = {'qwen': DQwen.GGUF, 'phi': DPhi.GGUF, 'qwenv': DQwenV.GGUF}
        self.projector = DQwenV.MMPROJ
        (self.root / 'models').mkdir()
        for name in [*self.models.values(), self.projector]:
            (self.root / 'models' / name).touch()
        self.executable(self.bin / 'sudo', '#!/bin/sh\nexec "$@"\n')
        self.executable(self.bin / 'sleep', '#!/bin/sh\nexit 0\n')
        self.executable(self.bin / 'systemctl', '''#!/bin/sh
printf 'systemctl %s\n' "$*" >> "$TEST_LOG"
if [ "$1" = show ]; then echo loaded; fi
''')
        self.executable(self.bin / 'chgrp', '''#!/bin/sh
printf 'chgrp %s\n' "$*" >> "$TEST_LOG"
''')
        # Preserve real install modes and file copies; omit privileged ownership.
        self.executable(self.bin / 'install', '''#!/usr/bin/python3
import os, subprocess, sys
args = iter(sys.argv[1:])
clean = []
for arg in args:
    if arg in ('-o', '-g'):
        next(args)
    else:
        clean.append(arg)
assert os.path.realpath(clean[-1]).startswith(os.environ['TEST_ROOT'] + '/')
raise SystemExit(subprocess.call(['/usr/bin/install', *clean]))
''')
        self.executable(self.bin / 'python3', '''#!/bin/bash
if [[ ${1:-} == -m && ${2:-} == venv ]]; then
    mkdir -p "$3/bin"
    cp "$TEST_ROOT/venv-python" "$3/bin/python"
    exit 0
fi
exec /usr/bin/python3 "$@"
''')
        self.executable(self.root / 'venv-python', '''#!/bin/sh
printf 'python %s\n' "$*" >> "$TEST_LOG"
if [ "${TEST_FAIL:-}" = pip ] && [ "$2" = pip ]; then exit 41; fi
if [ "${TEST_FAIL:-}" = chrome ] && [ "$1" != -m ]; then exit 42; fi
''')
        self.executable(self.bin / 'systemd-analyze', '''#!/bin/sh
printf 'verify\n' >> "$TEST_LOG"
if [ "${TEST_FAIL:-}" = verify ]; then exit 43; fi
exec /usr/bin/systemd-analyze "$@"
''')

    def executable(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        path.chmod(0o755)

    def prepare(self, environment, old=False):
        self.app = self.root / ('ax3l_prod' if environment == 'dev' else f'{environment}/ax3l')
        self.config = self.root / ('prod_etc/ax3l' if environment == 'dev' else 'etc/ax3l')
        self.app.mkdir(parents=True, exist_ok=True)
        self.config.mkdir(parents=True, exist_ok=True)
        self.config.chmod(0o700)
        self.credentials = self.config / 'database.env'
        self.credentials.write_text('DB_PASSWORD=fixture-secret\n')
        self.credentials.chmod(0o600)
        if old:
            self.executable(self.app / '.venv/bin/python', (self.root / 'venv-python').read_text())
            library = self.app / '.venv/lib/package.py'
            library.parent.mkdir()
            library.write_text('# fixture\n')
            library.chmod(0o600)
            for path in (self.app / '.venv').rglob('*'):
                if path.is_dir() or path.name == 'python':
                    path.chmod(0o700)
            (self.app / '.venv').chmod(0o700)

    def run_installer(self, *args, fail='', euid=None):
        environment = args[1] if len(args) > 1 else 'dev'
        env = dict(os.environ, PATH=f'{self.bin}:{os.environ["PATH"]}',
                   TEST_ROOT=str(self.root), TEST_LOG=str(self.log), TEST_FAIL=fail,
                   TEST_EUID=str(euid if euid is not None else (1000 if environment == 'dev' else 0)),
                   PYTHONDONTWRITEBYTECODE='1')
        return subprocess.run(['bash', '-c', 'umask 077; exec bash "$@"', 'fixture',
                               str(self.root / 'scripts/install-services.sh'), *args],
                              env=env, capture_output=True, text=True, timeout=30)

    def test_install_and_upgrade_all_environments_and_models(self):
        for environment, suffix in [('dev', '-dev'), ('qa', '-qa'), ('prod', '')]:
            self.prepare(environment, old=True)
            for model in self.models:
                with self.subTest(environment=environment, model=model):
                    self.log.write_text('')
                    legacy = self.units / f'llm-server{suffix}.service'
                    legacy.touch()
                    result = self.run_installer('-env', environment, '-model', model)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertFalse(legacy.exists())
                    for name in ('qwen-server', 'phi-server', 'qwenv-server', 'ax3l-server', 'reporting-server', 'watchdog'):
                        unit = self.units / f'{name}{suffix}.service'
                        self.assertEqual(unit.stat().st_mode & 0o777, 0o644)
                        self.assertNotIn('@', unit.read_text())
                    self.assertEqual(self.credentials.stat().st_mode & 0o777, 0o600)
                    self.assertEqual(self.credentials.read_text(), 'DB_PASSWORD=fixture-secret\n')
                    self.assertEqual(self.config.stat().st_mode & 0o777, 0o750)
                    self.assertEqual((self.config / 'mcp.json').stat().st_mode & 0o777, 0o640)
                    mcp = json.loads((self.config / 'mcp.json').read_text())['mcpServers']['snakelab']
                    self.assertEqual(mcp['command'], str(self.app / '.venv/bin/python'))
                    from ax3l.constants.DAx3l import DAx3l
                    self.assertEqual(mcp['env']['AX3L_ZMQ_ENDPOINT'], getattr(DAx3l, 'ZMQ_ENDPOINT' + ('' if environment == 'prod' else '_' + environment.upper())))
                    self.assertEqual((self.app / '.venv/lib/package.py').stat().st_mode & 0o777, 0o640)
                    self.assertEqual((self.app / '.venv/bin/python').stat().st_mode & 0o777, 0o750)
                    self.assertTrue((self.app / 'ax3l/app/snakelab/tools/__main__.py').is_file())
                    calls = self.log.read_text()
                    self.assertLess(calls.index('verify'), calls.index('systemctl stop'))
                    self.assertIn(f'systemctl start {model}-server{suffix}.service', calls)
                    self.assertIn(f'systemctl disable --now llm-server{suffix}.service', calls)
                    self.assertIn('chgrp -R ax3l', calls)

    def test_fresh_install_and_default_model(self):
        self.prepare('dev')
        result = self.run_installer('-env', 'dev')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.app / '.venv').stat().st_mode & 0o777, 0o755)
        self.assertIn('systemctl start qwen-server-dev.service', self.log.read_text())

    def test_provisioning_failures_do_not_stop_services(self):
        self.prepare('dev')
        for failure in ('pip', 'chrome', 'verify'):
            with self.subTest(failure=failure):
                self.log.write_text('')
                result = self.run_installer('-env', 'dev', fail=failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('systemctl', self.log.read_text())
                self.assertEqual(list(self.units.iterdir()), [])

    def test_invalid_arguments_and_wrong_user_do_not_touch_services(self):
        for args, euid in [((), 1000), (('-env',), 1000), (('-env', 'bad'), 1000),
                           (('-env', 'dev', '-model', 'bad'), 1000),
                           (('-env', 'dev'), 0), (('-env', 'prod'), 1000),
                           (('-env', 'qa'), 1000)]:
            with self.subTest(args=args, euid=euid):
                result = self.run_installer(*args, euid=euid)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('unbound variable', result.stderr)
                self.assertFalse(self.log.exists())

    def test_missing_prerequisites_do_not_touch_services(self):
        result = self.run_installer('-env', 'dev')
        self.assertIn('Run install.sh', result.stderr)
        self.prepare('prod')
        for name, model in [(self.projector, 'qwenv'), (self.models['qwen'], 'qwen')]:
            (self.root / 'models' / name).unlink()
            result = self.run_installer('-env', 'prod', '-model', model)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('first.', result.stderr)
        self.assertFalse(self.log.exists())
