"""Run installer orchestration in a disposable checkout with host actions stubbed.

Only absolute host paths and EUID checks are redirected in the fixture script.
Rendering, file copying, chmod, and systemd validation are real.
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
        for name in ('install-services.sh', 'service-configuration.sh', 'restart.sh', 'uninstall.sh'):
            script = self.root / 'scripts' / name
            script.write_text(script.read_text().replace('$EUID', '$TEST_EUID')
                              .replace('/opt/prod/ax3l', str(self.root / 'app'))
                              .replace('config_dir=/etc/ax3l', f'config_dir={self.root}/etc/ax3l')
                              .replace('/etc/systemd/system', str(self.units)))
        constants = self.root / 'ax3l/constants/DAx3l.py'
        constants.write_text(constants.read_text().replace('/opt/prod/ax3l', str(self.root / 'app')))
        helper = self.root / 'scripts/services.sh'
        helper.write_text(helper.read_text().replace('$EUID', '$TEST_EUID'))
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

    def prepare(self, old=False):
        self.app = self.root / 'app'
        self.config = self.root / 'etc/ax3l'
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

    def run_installer(self, *args, fail='', euid=None, script='install-services.sh'):
        env = dict(os.environ, PATH=f'{self.bin}:{os.environ["PATH"]}',
                   TEST_ROOT=str(self.root), TEST_LOG=str(self.log), TEST_FAIL=fail,
                   TEST_EUID=str(euid if euid is not None else 0),
                   PYTHONDONTWRITEBYTECODE='1')
        return subprocess.run(['bash', '-c', 'umask 077; exec bash "$@"', 'fixture',
                               str(self.root / 'scripts' / script), *args],
                              env=env, capture_output=True, text=True, timeout=30)

    def test_install_and_upgrade_manage_only_ax3l_services(self):
        self.prepare(old=True)
        shared = self.units / 'llamasrv-llm.service'
        shared.write_text('# independently managed inference\n')
        for iteration in range(2):
            with self.subTest(iteration=iteration):
                self.log.write_text('')
                result = self.run_installer()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual({path.name for path in self.units.iterdir()}, {
                    'ax3l-server.service', 'reporting-server.service',
                    'watchdog.service', 'llamasrv-llm.service',
                })
                self.assertEqual(shared.read_text(), '# independently managed inference\n')
                for name in ('ax3l-server', 'reporting-server', 'watchdog'):
                    unit = self.units / f'{name}.service'
                    self.assertEqual(unit.stat().st_mode & 0o777, 0o644)
                    self.assertNotIn('@', unit.read_text())
                self.assertEqual(self.credentials.stat().st_mode & 0o777, 0o600)
                self.assertEqual(self.credentials.read_text(), 'DB_PASSWORD=fixture-secret\n')
                self.assertEqual(self.config.stat().st_mode & 0o777, 0o750)
                self.assertEqual((self.app / '.venv/lib/package.py').stat().st_mode & 0o777, 0o640)
                self.assertEqual((self.app / '.venv/bin/python').stat().st_mode & 0o777, 0o750)
                for module in ('app/snakelab/tools/__main__.py', 'activity/SimulationAnimation.py',
                               'activity/fonts/DejaVuSansMono.ttf', 'activity/fonts/LICENSE.txt',
                               'interface/SimulationGifStore.py', 'interface/SimulationConfiguration.py',
                               'activity/RunAnalysis.py', 'entities/ConfigurationDraft.py',
                               'entities/SimulationAnalysis.py', 'app/snakelab/AnalyzeRun.py',
                               'app/snakelab/ExperimentDb.py', 'app/snakelab/knowledge/choose-snake-setting/SKILL.md',
                               'app/snakelab/prompts/ConfigurationChoice.py',
                               'app/snakelab/SubmitSimulationSummaryHandler.py',
                               'app/snakelab/tools/SubmitSimulationSummary.py',
                               'app/snakelab/SelectParameterHandler.py', 'app/snakelab/tools/SelectParameter.py',
                               'app/snakelab/RunSimulationHandler.py', 'app/snakelab/tools/RunSimulation.py',
                               'app/snakelab/prompts/ConfigurationNextStep.py',
                               'interface/KnowledgeBase.py', 'constants/DSimulationAnalysis.py',
                               'interface/SimulationData.py', 'activity/SimulationDataPages.py',
                               'activity/ParameterRules.py', 'constants/DChoice.py',
                               'app/snakelab/tools/ReadSimulationData.py',
                               'app/snakelab/knowledge/index.md',
                               'app/snakelab/knowledge/analysis/index.md',
                               'app/snakelab/knowledge/analysis/scores.md',
                               'app/snakelab/knowledge/analysis/distribution.md',
                               'app/snakelab/knowledge/analysis/loss.md',
                               'app/snakelab/prompts/FirstContactEpsilonNicePair.py',
                               'app/snakelab/prompts/ComparisonEpsilonNicePair.py', 'app/ReportBackground.py'):
                    self.assertTrue((self.app / 'ax3l' / module).is_file(), module)
                reporting = (self.units / 'reporting-server.service').read_text()
                self.assertIn(f'--gif-dir {self.app}/games', reporting)
                self.assertIn('--port 28870', reporting)
                self.assertIn(f'ReadWritePaths={self.app}/games', reporting)
                self.assertTrue((self.app / 'games').is_dir())
                application = (self.units / 'ax3l-server.service').read_text()
                self.assertIn('--zmq-endpoint tcp://127.0.0.1:61970', application)
                self.assertIn('--output /var/lib/ax3l/snakelab', application)
                self.assertIn('RuntimeDirectory=ax3l', application)
                self.assertIn('Environment=XDG_CONFIG_HOME=/run/ax3l/chrome-config', application)
                self.assertIn('Environment=XDG_CACHE_HOME=/run/ax3l/chrome-cache', application)
                calls = self.log.read_text()
                self.assertLess(calls.index('verify'), calls.index('systemctl stop'))
                self.assertNotIn('llamasrv', calls)
                self.assertNotIn('sleep', calls)
                self.assertIn('chgrp -R ax3l', calls)
                starts = [line for line in calls.splitlines() if line.startswith('systemctl start')]
                self.assertEqual(starts, ['systemctl start reporting-server.service',
                                          'systemctl start ax3l-server.service',
                                          'systemctl start watchdog.service'])

    def test_fresh_install_needs_no_model_binary_or_files(self):
        self.prepare()
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.app / '.venv').stat().st_mode & 0o777, 0o755)
        for module in ('app/ReportBackground.py', 'app/ReportingDb.py', 'app/ReportingRefresh.py',
                       'activity/CompletedRounds.py'):
            self.assertTrue((self.app / 'ax3l' / module).is_file(), module)
        config = json.loads((self.app / 'conf/ax3l.json').read_text())
        self.assertEqual(config['llamasrv_url'], 'http://127.0.0.1:51001')
        self.assertEqual(set(config['network']), {'report', 'zmq'})

    def test_provisioning_failures_do_not_stop_services(self):
        self.prepare()
        for failure in ('pip', 'chrome', 'verify'):
            with self.subTest(failure=failure):
                self.log.write_text('')
                result = self.run_installer(fail=failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('systemctl', self.log.read_text())
                self.assertEqual(list(self.units.iterdir()), [])

    def test_invalid_arguments_and_wrong_user_do_not_touch_services(self):
        for args, euid in [((), 1000), (('-unknown',), 0), (('-unknown', 'value'), 0),
                           (('-model',), 0), (('-model', 'qwen', 'extra'), 0),
                           (('-model', 'bad'), 0), (('-model', 'phi'), 1000)]:
            with self.subTest(args=args, euid=euid):
                result = self.run_installer(*args, euid=euid)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('unbound variable', result.stderr)
                self.assertFalse(self.log.exists())

    def test_missing_installation_does_not_touch_services(self):
        result = self.run_installer()
        self.assertIn('Run install.sh', result.stderr)
        self.assertFalse(self.log.exists())

    def test_restart_applies_all_bindings_without_provisioning_and_preserves_config(self):
        self.prepare(old=True)
        path = self.app / 'conf/ax3l.json'
        path.parent.mkdir()
        content = json.dumps({'network': {
            'report': {'interface': '127.0.0.3', 'port': 28871},
            'zmq': {'interface': '0.0.0.0', 'port': 61971},
        }, 'llamasrv_url': 'http://wintermute:51001'}, indent=4)
        path.write_text(content)
        result = self.run_installer(script='restart.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(path.read_text(), content)
        self.assertIn('--host 127.0.0.3 --port 28871', (self.units / 'reporting-server.service').read_text())
        application = (self.units / 'ax3l-server.service').read_text()
        self.assertNotIn('--llm-url', application)
        self.assertIn('--zmq-endpoint tcp://0.0.0.0:61971', application)
        watchdog = (self.units / 'watchdog.service').read_text()
        self.assertNotIn('--llm', watchdog)
        calls = self.log.read_text()
        self.assertNotIn('python ', calls)
        self.assertNotIn('llamasrv', calls)
        self.assertLess(calls.index('verify'), calls.index('systemctl stop'))
        self.assertLess(calls.index('systemctl daemon-reload'), calls.index('systemctl start reporting-server'))

    def test_invalid_config_leaves_services_and_file_untouched(self):
        self.prepare(old=True)
        path = self.app / 'conf/ax3l.json'
        path.parent.mkdir()
        path.write_text('{"llamasrv_url": "http://wintermute/v1"}')
        content = path.read_bytes()
        for script in ('install-services.sh', 'restart.sh'):
            with self.subTest(script=script):
                result = self.run_installer(script=script)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('llamasrv_url', result.stderr)
                self.assertFalse(self.log.exists())
                self.assertEqual(path.read_bytes(), content)
                self.assertEqual(list(self.units.iterdir()), [])

    def test_retired_model_option_is_rejected_before_any_host_actions(self):
        for script in ('install-services.sh', 'restart.sh', 'upgrade.sh'):
            with self.subTest(script=script):
                result = self.run_installer('-model', 'qwen', script=script)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(self.log.exists())

    def test_uninstall_preserves_shared_inference(self):
        self.prepare()
        self.credentials.write_text('DB_NAME=ax3l\n')
        for name in ('watchdog', 'ax3l-server', 'reporting-server', 'llamasrv-llm', 'llamasrv-http'):
            (self.units / f'{name}.service').write_text('# fixture\n')
        self.executable(self.bin / 'mariadb', '#!/bin/sh\ncat >/dev/null\n')
        self.executable(self.bin / 'getent', '#!/bin/sh\nexit 2\n')
        result = self.run_installer(script='uninstall.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.app.exists())
        self.assertFalse(self.credentials.exists())
        self.assertEqual({path.name for path in self.units.iterdir()},
                         {'llamasrv-llm.service', 'llamasrv-http.service'})
        self.assertNotIn('llamasrv', self.log.read_text())
