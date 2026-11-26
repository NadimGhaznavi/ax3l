"""Run installer orchestration in a disposable checkout with host actions stubbed.

Only absolute host paths and EUID checks are redirected in the fixture script.
Rendering, file copying, chmod, and systemd validation are real.
Package/browser provisioning, ownership changes, and systemctl are simulated.
Set AX3L_TEST_INSTALL_DB=1 to also exercise a full install/uninstall/reinstall
against a private MariaDB instance created inside the test directory.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
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
        for name in ('install.sh', 'install-services.sh', 'service-configuration.sh', 'restart.sh', 'uninstall.sh'):
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
        self.executable(self.bin / 'getent', '''#!/bin/sh
if [ "${TEST_EXISTING_LINUX:-}" = "$1" ]; then exit 0; fi
exit 2
''')
        for command in ('groupadd', 'useradd', 'groupdel', 'userdel'):
            self.executable(self.bin / command, f'''#!/bin/sh
printf '{command} %s\\n' "$*" >> "$TEST_LOG"
''')
        self.executable(self.bin / 'mariadb', '''#!/usr/bin/python3
import os, sys
from pathlib import Path
args = sys.argv[1:]
if '-e' in args:
    sql = args[args.index('-e') + 1]
    print(os.environ.get('TEST_EXISTING_DATABASE', '0') if 'SCHEMATA' in sql else '1')
else:
    sql = sys.stdin.read()
    with Path(os.environ['TEST_ROOT'], 'database.sql').open('a') as stream:
        stream.write(sql)
with Path(os.environ['TEST_LOG']).open('a') as stream:
    stream.write('mariadb ' + sql + '\\n')
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

    def run_installer(self, *args, fail='', euid=None, script='install-services.sh', extra_env=None):
        env = dict(os.environ, PATH=f'{self.bin}:{os.environ["PATH"]}',
                   TEST_ROOT=str(self.root), TEST_LOG=str(self.log), TEST_FAIL=fail,
                   TEST_EUID=str(euid if euid is not None else 0),
                   PYTHONDONTWRITEBYTECODE='1')
        env.update(extra_env or {})
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
                for module in ('presentation/reporting/SimulationAnimation.py',
                               'presentation/reporting/fonts/DejaVuSansMono.ttf', 'presentation/reporting/fonts/LICENSE.txt',
                               'interface/SimulationGifStore.py', 'interface/SimulationConfiguration.py',
                               'interface/schemas/simulation-config-v2.schema.json',
                               'interface/ReportHandler.py', 'interface/database/EventSchema.py',
                               'interface/database/EventLogDb.py', 'interface/database/DbMgr.py',
                               'app/reporting/Reports.py', 'presentation/reporting/ReportRenderer.py',
                               'constants/DScoreDistribution.py',
                               'presentation/reporting/PresentationValues.py', 'app/reporting/ReportBackground.py',
                               'app/experiment/ExperimentLoop.py', 'interface/database/ExperimentDb.py',
                               'interface/ViewConversation.py', 'entities/ExperimentState.py',
                               'entities/ExperimentView.py', 'entities/ViewProposal.py',
                               'presentation/ViewPrompts.py',
                               'presentation/RunComparisonImage.py', 'activity/ScorePercentiles.py',
                               'activity/ExplorationProgress.py', 'activity/RewardProgress.py', 'activity/TrainingProgress.py',
                               'constants/DViewConversation.py'):
                    self.assertTrue((self.app / 'ax3l' / module).is_file(), module)
                reporting = (self.units / 'reporting-server.service').read_text()
                self.assertIn(f'--gif-dir {self.app}/games', reporting)
                self.assertIn('--port 28870', reporting)
                self.assertIn(f'ReadWritePaths={self.app}/games', reporting)
                self.assertTrue((self.app / 'games').is_dir())
                for asset in (ROOT / 'ax3l/presentation/reporting/templates').glob('*.html'):
                    installed = self.app / 'ax3l/presentation/reporting/templates' / asset.name
                    self.assertEqual(installed.read_bytes(), asset.read_bytes(), str(asset))
                for asset in (ROOT / 'ax3l/presentation/prompts').rglob('*.md'):
                    installed = self.app / asset.relative_to(ROOT)
                    self.assertEqual(installed.read_bytes(), asset.read_bytes(), str(asset))
                smoke = subprocess.run([sys.executable, '-c', '''
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from ax3l.interface.SimulationConfiguration import SimulationConfiguration
from ax3l.entities.ExperimentView import VIEWS
from ax3l.presentation.ViewPrompts import ViewPrompts
from ax3l.server.Ax3lServer import main
from ax3l.server.ReportingServer import make_server
from ax3l.presentation.reporting.ReportRenderer import ReportRenderer
ReportRenderer()
assert SimulationConfiguration.defaults()['model']['hidden_size'] == 64
templates = Environment(loader=FileSystemLoader(Path('ax3l/presentation/reporting/templates')))
assert templates.get_template('events.html')
for view in VIEWS.values():
    context = dict(
        previous_hypothesis='The proposed adjustment will improve the high score.',
        previous_values={},
        previous_observations='Comparison measurements are not available yet.',
        reference_run_id='golden-run', latest_run_id='latest-run',
        reference_episodes=[{'episode': 1, 'score': 0, 'epsilon': .5, 'steps': 10, 'epsilon_nice_injections': 0, 'outcome': 'wall', 'loss': None}],
        latest_episodes=[{'episode': 1, 'score': 4, 'epsilon': 0, 'steps': 10, 'epsilon_nice_injections': 2, 'outcome': 'snake', 'loss': .4}],
        reference_high_score=0, latest_high_score=4,
        parameters={},
        other_parameters={'seed': 1971, 'model': {'layers': '2 (draft)'}},
    )
    content = ViewPrompts().render(view, context)
    assert content
    assert isinstance(content, str)
    assert ViewPrompts().render_evaluation(view, context)[1]['type'] == 'image_url'
'''], cwd=self.app, env=dict(os.environ, PYTHONPATH=str(self.app), PYTHONDONTWRITEBYTECODE='1'),
                    capture_output=True, text=True, timeout=10)
                self.assertEqual(smoke.returncode, 0, smoke.stderr)
                application = (self.units / 'ax3l-server.service').read_text()
                self.assertIn('--zmq-endpoint tcp://127.0.0.1:61970', application)
                self.assertNotIn('--output', application)
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
        for module in ('app/reporting/ReportBackground.py', 'interface/database/ReportingDb.py', 'app/ReportingRefresh.py'):
            self.assertTrue((self.app / 'ax3l' / module).is_file(), module)
        config = json.loads((self.app / 'conf/ax3l.json').read_text())
        self.assertEqual(config['llamasrv_url'], 'http://127.0.0.1:51001')
        self.assertEqual(set(config['network']), {'report', 'zmq'})

    def test_asset_discovery_failure_prevents_service_activation(self):
        self.prepare()
        previous = self.app / 'ax3l/previous.py'
        previous.parent.mkdir()
        previous.write_text('previous application')
        self.executable(self.bin / 'find', '''#!/bin/sh
printf 'Application file discovery failed.\\n' >&2
exit 44
''')
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Application file discovery failed.', result.stderr)
        calls = self.log.read_text()
        self.assertIn('systemctl stop ax3l-server.service', calls)
        self.assertNotIn('systemctl daemon-reload', calls)
        self.assertNotIn('systemctl start', calls)
        self.assertEqual(list(self.units.iterdir()), [])
        self.assertEqual(previous.read_text(), 'previous application')
        self.assertEqual(list(self.app.glob('.application.*')), [])

    def test_upgrade_replaces_the_package_and_preserves_runtime_data(self):
        self.prepare(old=True)
        previous = self.app / 'ax3l/retired.py'
        previous.parent.mkdir()
        previous.write_text('retired application module')
        games = self.app / 'games'
        games.mkdir()
        (games / 'saved.gif').write_bytes(b'saved animation')
        result = self.run_installer(script='upgrade.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(previous.exists())
        self.assertTrue((self.app / 'ax3l/server/Ax3lServer.py').is_file())
        self.assertEqual((games / 'saved.gif').read_bytes(), b'saved animation')
        self.assertTrue((self.app / 'conf/ax3l.json').is_file())
        self.assertEqual(list(self.app.glob('.application.*')), [])

    def test_package_replacement_failure_restores_the_previous_package(self):
        self.prepare(old=True)
        previous = self.app / 'ax3l/previous.py'
        previous.parent.mkdir()
        previous.write_text('previous application')
        self.executable(self.bin / 'mv', '''#!/bin/sh
case "$2" in
    */.application.*/ax3l) exit 44 ;;
esac
exec /usr/bin/mv "$@"
''')
        result = self.run_installer(script='upgrade.sh')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(previous.read_text(), 'previous application')
        self.assertEqual(list(self.app.glob('.application.*')), [])
        self.assertNotIn('systemctl start', self.log.read_text())

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

    def test_installer_rejects_existing_resources_without_changing_them(self):
        self.prepare()
        credentials = self.credentials.read_bytes()
        result = self.run_installer(script='install.sh')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('uninstall.sh', result.stderr)
        self.assertFalse(self.log.exists())
        self.assertEqual(self.credentials.read_bytes(), credentials)

        self.app.rmdir()
        for name in ('ax3l-server', 'reporting-server', 'watchdog'):
            with self.subTest(unit=name):
                unit = self.units / f'{name}.service'
                unit.write_text('# existing installation\n')
                result = self.run_installer(script='install.sh')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('uninstall.sh', result.stderr)
                self.assertFalse(self.log.exists())
                self.assertEqual(unit.read_text(), '# existing installation\n')
                unit.unlink()

        for kind in ('passwd', 'group'):
            with self.subTest(linux_resource=kind):
                result = self.run_installer(script='install.sh', extra_env={'TEST_EXISTING_LINUX': kind})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('uninstall.sh', result.stderr)
                self.assertFalse(self.log.exists())
                self.assertFalse(self.app.exists())
        self.assertEqual(self.credentials.read_bytes(), credentials)

    def test_installer_rejects_existing_database_before_provisioning(self):
        result = self.run_installer(script='install.sh', extra_env={'TEST_EXISTING_DATABASE': '1'})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('uninstall.sh', result.stderr)
        self.assertFalse((self.root / 'app').exists())
        self.assertFalse((self.root / 'etc/ax3l').exists())
        calls = self.log.read_text()
        self.assertIn('mysql.user', calls)
        self.assertNotIn('groupadd', calls)
        self.assertNotIn('CREATE ', calls)
        self.assertNotIn('systemctl', calls)

    def test_fresh_install_reuses_retained_credentials(self):
        self.prepare()
        self.app.rmdir()
        saved = ('DB_HOST=localhost\nDB_PORT=3306\nDB_NAME=ax3l\nDB_USER=ax3l\n'
                 f'DB_PASSWORD={"a" * 64}\n')
        self.credentials.write_text(saved)
        result = self.run_installer(script='install.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.credentials.read_text(), saved)
        self.assertEqual(self.credentials.stat().st_mode & 0o777, 0o600)
        sql = (self.root / 'database.sql').read_text()
        self.assertIn('CREATE DATABASE `ax3l`;', sql)
        self.assertIn(f"IDENTIFIED BY '{'a' * 64}'", sql)
        self.assertNotIn('DROP ', sql)
        self.assertNotIn('DELETE ', sql)
        self.assertTrue((self.app / 'conf/ax3l.json').is_file())
        self.assertNotIn('snake-lab.service', self.log.read_text())

    def test_fresh_install_saves_new_credentials(self):
        result = self.run_installer(script='install.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        credentials = self.root / 'etc/ax3l/database.env'
        self.assertRegex(credentials.read_text(), r'DB_PASSWORD=[a-f0-9]{64}\n$')
        self.assertEqual(credentials.stat().st_mode & 0o777, 0o600)

    @unittest.skipUnless(os.environ.get('AX3L_TEST_INSTALL_DB') == '1',
                         'requires opt-in private MariaDB installer check')
    def test_install_uninstall_reinstall_with_real_database(self):
        server_binary = Path('/usr/sbin/mariadbd')
        if not server_binary.is_file() or shutil.which('mariadb-install-db') is None:
            self.skipTest('requires MariaDB server and initialization tools')
        data = self.root / 'database'
        initialized = subprocess.run([
            'mariadb-install-db', '--no-defaults', f'--datadir={data}',
            '--auth-root-authentication-method=normal', '--skip-test-db',
            '--innodb-use-native-aio=0',
        ], capture_output=True, text=True, timeout=30)
        self.assertEqual(initialized.returncode, 0, initialized.stdout + initialized.stderr)
        socket = self.root / 'database.sock'
        with (self.root / 'database-server.log').open('w') as output:
            server = subprocess.Popen([
                str(server_binary), '--no-defaults', f'--datadir={data}',
                f'--socket={socket}', f'--pid-file={self.root / "database.pid"}',
                '--skip-networking', '--innodb-buffer-pool-size=32M',
                '--innodb-use-native-aio=0',
            ], stdout=output, stderr=subprocess.STDOUT)
        self.addCleanup(server.wait, timeout=10)
        self.addCleanup(server.terminate)
        admin = ['/usr/bin/mariadb', '--no-defaults', f'--socket={socket}',
                 '--user=root', '--batch', '--skip-column-names']
        deadline = time.monotonic() + 10
        while True:
            ready = subprocess.run([*admin, '-e', 'SELECT 1'], capture_output=True, text=True, timeout=5)
            if ready.returncode == 0:
                break
            if server.poll() is not None or time.monotonic() >= deadline:
                self.fail((self.root / 'database-server.log').read_text())
            time.sleep(0.1)

        def query(sql):
            result = subprocess.run([*admin, '-e', sql], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.strip()

        # The production database/account names are redirected only in this
        # disposable checkout, and every database connection uses its private socket.
        for name, old, new in (
            ('install.sh', 'DB_NAME=ax3l\n', 'DB_NAME=ax3l_test\n'),
            ('uninstall.sh', 'database=ax3l\n', 'database=ax3l_test\n'),
        ):
            path = self.root / 'scripts' / name
            path.write_text(path.read_text().replace(old, new))
        self.executable(self.bin / 'mariadb', '''#!/usr/bin/python3
import os, sys
args = [arg for arg in sys.argv[1:] if arg != '--no-defaults'
        and not arg.startswith(('--host=', '--port=', '--protocol=', '--socket='))]
if not any(arg.startswith('--user=') for arg in args):
    args.insert(0, '--user=root')
os.execv('/usr/bin/mariadb', ['mariadb', '--no-defaults', *args, '--protocol=socket',
         '--socket=' + os.environ['TEST_DATABASE_SOCKET']])
''')
        self.prepare()
        self.app.rmdir()
        saved = ('DB_HOST=localhost\nDB_PORT=3306\nDB_NAME=ax3l_test\nDB_USER=ax3l_test\n'
                 f'DB_PASSWORD={"a" * 64}\n')
        self.credentials.write_text(saved)
        extra_env = {'TEST_DATABASE_SOCKET': str(socket)}
        query('CREATE DATABASE snakelab_test; CREATE TABLE snakelab_test.simulation_runs '
              '(id INT PRIMARY KEY); INSERT INTO snakelab_test.simulation_runs VALUES (1)')

        for create, remove in (
            ('CREATE DATABASE ax3l_test', 'DROP DATABASE ax3l_test'),
            ("CREATE USER 'ax3l_test'@'localhost'", "DROP USER 'ax3l_test'@'localhost'"),
        ):
            with self.subTest(existing_resource=create):
                query(create)
                rejected = self.run_installer(script='install.sh', extra_env=extra_env)
                self.assertNotEqual(rejected.returncode, 0)
                self.assertIn('uninstall.sh', rejected.stderr)
                self.assertFalse(self.app.exists())
                self.assertEqual(self.credentials.read_text(), saved)
                query(remove)

        installed = self.run_installer(script='install.sh', extra_env=extra_env)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        query('CREATE TABLE ax3l_test.experiment_data (id INT PRIMARY KEY); '
              'INSERT INTO ax3l_test.experiment_data VALUES (1)')
        rejected = self.run_installer(script='install.sh', extra_env=extra_env)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(query('SELECT COUNT(*) FROM ax3l_test.experiment_data'), '1')

        removed = self.run_installer(script='uninstall.sh', extra_env=extra_env)
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertEqual(self.credentials.read_text(), saved)
        self.assertEqual(query("SELECT COUNT(*) FROM information_schema.SCHEMATA "
                               "WHERE SCHEMA_NAME = 'ax3l_test'"), '0')
        self.assertEqual(query("SELECT COUNT(*) FROM mysql.user WHERE User = 'ax3l_test'"), '0')
        reinstalled = self.run_installer(script='install.sh', extra_env=extra_env)
        self.assertEqual(reinstalled.returncode, 0, reinstalled.stderr)
        self.assertEqual(self.credentials.read_text(), saved)
        self.assertEqual(query("SELECT COUNT(*) FROM information_schema.TABLES "
                               "WHERE TABLE_SCHEMA = 'ax3l_test'"), '0')
        self.assertEqual(query('SELECT COUNT(*) FROM snakelab_test.simulation_runs'), '1')
        self.assertNotIn('snake-lab.service', self.log.read_text())

    def test_uninstall_preserves_credentials_and_shared_inference(self):
        self.prepare()
        self.credentials.write_text('DB_NAME=ax3l\n')
        for name in ('watchdog', 'ax3l-server', 'reporting-server', 'llamasrv-llm', 'llamasrv-http'):
            (self.units / f'{name}.service').write_text('# fixture\n')
        self.executable(self.bin / 'mariadb', '#!/bin/sh\ncat >/dev/null\n')
        self.executable(self.bin / 'getent', '#!/bin/sh\nexit 2\n')
        result = self.run_installer(script='uninstall.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.app.exists())
        self.assertEqual(self.credentials.read_text(), 'DB_NAME=ax3l\n')
        self.assertEqual(self.credentials.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o700)
        self.assertEqual({path.name for path in self.units.iterdir()},
                         {'llamasrv-llm.service', 'llamasrv-http.service'})
        self.assertNotIn('llamasrv', self.log.read_text())
