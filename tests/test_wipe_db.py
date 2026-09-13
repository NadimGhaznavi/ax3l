"""Exercise reset orchestration without touching services or live databases."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WipeDbTests(unittest.TestCase):
    def run_script(self, environment='prod', *, fail_stop=False, fail_wipe=False):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            scripts = {
                'id': '#!/bin/sh\necho 0\n',
                'mariadb': '#!/bin/sh\nprintf "db %s\\n" "$*" >> "$CALLS"\ncase "$*" in *--execute=*) exit 0;; esac\ncat > "$SQL_FILE"\nif [ "$FAIL_WIPE" = 1 ]; then exit 1; fi\nprintf "wipe committed\\n" >> "$CALLS"\n',
                'systemctl': '#!/bin/sh\nprintf "service %s\\n" "$*" >> "$CALLS"\nif [ "$1" = show ]; then echo loaded; fi\nif [ "$1" = stop ] && [ "$FAIL_STOP" = 1 ]; then exit 1; fi\n',
            }
            for name, content in scripts.items():
                path = directory / name
                path.write_text(content)
                path.chmod(0o755)
            env = dict(os.environ, PATH=f'{folder}:{os.environ["PATH"]}',
                       CALLS=str(directory / 'calls'), SQL_FILE=str(directory / 'sql'),
                       FAIL_STOP=str(int(fail_stop)), FAIL_WIPE=str(int(fail_wipe)))
            result = subprocess.run(['bash', str(ROOT / 'scripts/wipe-db.sh'), '-env', environment],
                                    env=env, capture_output=True, text=True)
            return result, (directory / 'calls').read_text() if (directory / 'calls').exists() else '', (directory / 'sql').read_text() if (directory / 'sql').exists() else ''

    def test_both_databases_cleared_after_services_stop(self):
        for environment, database, suffix in (('dev', 'ax3l_dev', '-dev'), ('qa', 'ax3l_qa', '-qa'), ('prod', 'ax3l', '')):
            with self.subTest(environment=environment):
                result, calls, sql = self.run_script(environment)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f'service stop ax3l-server{suffix}.service', calls)
                self.assertIn('service stop snake-lab.service', calls)
                self.assertLess(calls.index('service stop snake-lab.service'), calls.rindex('db '))
                self.assertIn(f'DELETE FROM `{database}`.events;', sql)
                self.assertIn('DELETE FROM snakelab.simulation_runs;', sql)
                self.assertTrue(sql.startswith('START TRANSACTION;'))
                self.assertTrue(sql.endswith('COMMIT;\n'))
                self.assertIn(f'ALTER TABLE `{database}`.events AUTO_INCREMENT = 1;', calls)
                self.assertIn('ALTER TABLE snakelab.simulation_runs AUTO_INCREMENT = 1;', calls)
                self.assertLess(calls.index('wipe committed'), calls.index('ALTER TABLE'))
                self.assertNotIn('ALTER TABLE', sql)
                self.assertNotIn('DROP ', sql)
                self.assertNotIn('service start', calls)

    def test_failed_stop_prevents_wipe(self):
        result, calls, sql = self.run_script(fail_stop=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sql, '')
        self.assertNotIn('ALTER TABLE', calls)

    def test_failed_wipe_prevents_counter_reset(self):
        result, calls, _ = self.run_script(fail_wipe=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('ALTER TABLE', calls)
        self.assertNotIn('Cleared ', result.stdout)

    def test_invalid_environment_does_nothing(self):
        result, calls, sql = self.run_script('unknown')
        self.assertEqual(result.returncode, 2)
        self.assertEqual((calls, sql), ('', ''))
