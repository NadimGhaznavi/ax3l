"""Check workspace reset boundaries without touching host services."""

from contextlib import redirect_stderr
from dataclasses import asdict
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from pymysql import IntegrityError

from ax3l.app.DbMgr import DbMgr
from ax3l.app.snakelab.ExperimentDb import ExperimentDb
from ax3l.app.snakelab.WipeExperimentWorkspace import main
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


ROOT = Path(__file__).resolve().parents[1]


class WorkspaceResetTests(unittest.TestCase):
    def store(self, phase='choosing', run_id=None):
        db = object.__new__(DbMgr)
        db._connection = Mock()
        db.execute = Mock(return_value=7)
        draft = ConfigurationDraft('private-draft', 'gold', {}, SimulationConfiguration.defaults(),
                                   ['learning_rate'], phase, run_id=run_id, parameter='food')
        db.query = Mock(return_value=[dict(content=json.dumps(asdict(draft)))])
        return db, ExperimentDb(db)

    def test_only_unsubmitted_setup_events_are_deleted_in_one_transaction(self):
        for phase in ('preparing', 'selecting_parameter', 'choosing', 'reviewing', 'ready'):
            with self.subTest(phase=phase):
                db, store = self.store(phase)
                self.assertEqual(store.wipe_workspace(), ('private-draft', 7))
                update, delete = db.execute.call_args_list
                self.assertIn('SET e.parent_event_id = NULL', update.args[0])
                self.assertIn('DELETE e FROM events e JOIN event_messages', delete.args[0])
                self.assertIn('$.payload.draft_id', delete.args[0])
                self.assertEqual(delete.args[1], ('private-draft', 'Tool', 'tool_request_received', 'private-draft'))
                self.assertEqual(update.args[1], delete.args[1])
                db._connection.begin.assert_called_once()
                db._connection.commit.assert_called_once()
                db._connection.rollback.assert_not_called()

    def test_submissions_and_seed_rotations_cannot_be_wiped(self):
        for phase, run_id in (('rotating_seed', None), ('submitting', None),
                              ('submitted', 'run'), ('choosing', 'run')):
            with self.subTest(phase=phase, run_id=run_id):
                db, store = self.store(phase, run_id)
                with self.assertRaisesRegex(ValueError, 'Only an unsubmitted setup'):
                    store.wipe_workspace()
                db.execute.assert_not_called()
                db._connection.rollback.assert_called_once()
                db._connection.commit.assert_not_called()

    def test_empty_or_finished_workspaces_preserve_history(self):
        for phase in ('completed', 'failed', None):
            with self.subTest(phase=phase):
                db, store = self.store(phase)
                if phase is None:
                    db.query.return_value = []
                self.assertIsNone(store.wipe_workspace())
                db.execute.assert_not_called()

    def test_deletion_failure_rolls_back_parent_link_changes(self):
        db, store = self.store()
        db.execute.side_effect = [1, IntegrityError(1451, 'Referenced event')]
        with self.assertRaises(IntegrityError):
            store.wipe_workspace()
        db._connection.rollback.assert_called_once()
        db._connection.commit.assert_not_called()

    def test_cli_preflight_does_not_delete_and_always_closes_the_database(self):
        with patch('ax3l.app.snakelab.WipeExperimentWorkspace.DbMgr') as factory, \
                patch('ax3l.app.snakelab.WipeExperimentWorkspace.ExperimentDb') as store:
            self.assertEqual(main(['--check']), 0)
        factory.assert_called_once_with(initialize_event_tables=False)
        store.return_value.draft.assert_called_once_with()
        store.return_value.wipe_workspace.assert_not_called()
        factory.return_value.close.assert_called_once_with()

    def test_cli_reports_refusal_and_closes_the_database(self):
        with patch('ax3l.app.snakelab.WipeExperimentWorkspace.DbMgr') as factory, \
                patch('ax3l.app.snakelab.WipeExperimentWorkspace.ExperimentDb') as store, \
                redirect_stderr(StringIO()) as error:
            store.return_value.wipe_workspace.side_effect = ValueError('Submission already started.')
            self.assertEqual(main([]), 1)
        self.assertIn('Submission already started.', error.getvalue())
        factory.return_value.close.assert_called_once_with()


class WorkspaceResetScriptTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        scripts = self.folder / 'scripts'
        scripts.mkdir()
        self.script = scripts / 'wipe-experiment-workspace.sh'
        self.script.write_text((ROOT / 'scripts/wipe-experiment-workspace.sh').read_text()
                               .replace('/opt/prod/ax3l', str(self.folder / 'app'))
                               .replace('/etc/ax3l/database.env', str(self.folder / 'database.env')))
        services = scripts / 'services.sh'
        shutil.copy(ROOT / 'scripts/services.sh', services)
        services.write_text(services.read_text().replace('$EUID', '$TEST_EUID'))
        self.calls = self.folder / 'calls'
        self.password = f'$(touch {self.folder}/must-not-exist)'
        self.credentials = self.folder / 'database.env'
        self.credentials.write_text('DB_HOST=localhost\nDB_PORT=3306\nDB_NAME=ax3l\n'
                                    f'DB_USER=ax3l\nDB_PASSWORD={self.password}\n')
        self.executable(self.folder / 'bin/id', '#!/bin/sh\necho 0\n')
        self.executable(self.folder / 'bin/systemctl', '''#!/bin/sh
printf 'service %s\n' "$*" >> "$CALLS"
if [ "$1" = show ]; then echo loaded; fi
if [ "$1" = stop ] && [ "$FAIL_STOP" = 1 ]; then exit 1; fi
''')
        self.executable(self.folder / 'app/.venv/bin/python', '''#!/bin/sh
[ "$DB_PASSWORD" = "$EXPECTED_PASSWORD" ] || exit 9
case "$*" in
    *--check) printf 'preflight\n' >> "$CALLS"; [ "$FAIL_CHECK" = 0 ] ;;
    *) printf 'wipe\n' >> "$CALLS"; [ "$FAIL_WIPE" = 0 ] ;;
esac
''')

    def executable(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        path.chmod(0o755)

    def run_script(self, *arguments, fail_check=False, fail_stop=False, fail_wipe=False):
        env = dict(os.environ, PATH=f'{self.folder}/bin:{os.environ["PATH"]}',
                   CALLS=str(self.calls), TEST_EUID='0', EXPECTED_PASSWORD=self.password,
                   FAIL_CHECK=str(int(fail_check)), FAIL_STOP=str(int(fail_stop)), FAIL_WIPE=str(int(fail_wipe)))
        result = subprocess.run(['bash', str(self.script), *arguments], env=env, capture_output=True, text=True)
        calls = self.calls.read_text().splitlines() if self.calls.exists() else []
        return result, calls

    def test_services_stop_before_wiping_and_restart_after_success(self):
        result, calls = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([call for call in calls if 'service show' not in call], [
            'preflight', 'service stop watchdog.service', 'service stop ax3l-server.service',
            'service stop reporting-server.service', 'wipe', 'service start reporting-server.service',
            'service start ax3l-server.service', 'service start watchdog.service'])
        self.assertFalse((self.folder / 'must-not-exist').exists())
        self.assertNotIn('snake-lab', '\n'.join(calls))
        self.assertNotIn('llama', '\n'.join(calls))

    def test_failed_preflight_never_stops_services(self):
        result, calls = self.run_script(fail_check=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, ['preflight'])

    def test_failed_service_stop_prevents_wiping(self):
        result, calls = self.run_script(fail_stop=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('wipe', calls)
        self.assertFalse(any('service start' in call for call in calls))

    def test_failed_wipe_keeps_services_stopped(self):
        result, calls = self.run_script(fail_wipe=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('remain stopped', result.stderr)
        self.assertIn('wipe', calls)
        self.assertFalse(any('service start' in call for call in calls))

    def test_missing_credentials_fail_before_stopping_services(self):
        self.credentials.unlink()
        result, calls = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])

    def test_help_and_unknown_arguments_have_no_side_effects(self):
        for arguments, code in ((('--help',), 0), (('--unexpected',), 2)):
            result, calls = self.run_script(*arguments)
            self.assertEqual(result.returncode, code)
            self.assertEqual(calls, [])
