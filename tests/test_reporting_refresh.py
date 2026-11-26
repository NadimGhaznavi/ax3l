"""Reporting backfill, incremental processing, and atomicity on MariaDB.

Use AX3L_TEST_DB=1 and the disposable ax3l_test DB_* environment.
Temporary source/projection tables keep fixtures separate from persistent data.
"""

import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch
from uuid import uuid4

from ax3l.interface.database.DbMgr import DbMgr
from ax3l.interface.database.EventLogDb import EventLogDb
from ax3l.interface.database.ReportingDb import ReportingDb
from ax3l.app.reporting.ReportingRefresh import ReportingRefresh
from ax3l.constants.DSnakeLab import DSnakeLab


@unittest.skipUnless(os.environ.get("AX3L_TEST_DB") == "1", "requires disposable MariaDB test database")
class ReportingRefreshTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ["DB_NAME"], "ax3l_test")
        self.db = DbMgr()
        self.addCleanup(self.db.close)
        self.enterContext(patch.object(DSnakeLab, 'DATABASE', 'ax3l_test'))
        self.reports = ReportingDb(self.db)
        self.reports.initialize()
        for table in ('report_runs', 'report_state'):
            ddl = self.db.query(f"SHOW CREATE TABLE {table}")[0]['Create Table']
            self.db.execute(ddl.replace('CREATE TABLE', 'CREATE TEMPORARY TABLE', 1))
        self.db.execute("""CREATE TEMPORARY TABLE events (
            event_id BIGINT UNSIGNED PRIMARY KEY, name VARCHAR(100), category VARCHAR(50),
            log_level VARCHAR(10), process_id CHAR(36)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
        self.db.execute("""CREATE TEMPORARY TABLE event_messages (
            event_id BIGINT UNSIGNED PRIMARY KEY, content LONGTEXT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
        self.reports.initialize()
        self.db.execute("""CREATE TEMPORARY TABLE simulation_runs (
            id BIGINT UNSIGNED PRIMARY KEY, run_id CHAR(36) COLLATE utf8mb4_unicode_ci UNIQUE,
            status VARCHAR(16), high_score INT, started_at DATETIME(6), completed_at DATETIME(6)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
        self.db.execute("""CREATE TEMPORARY TABLE simulation_episodes (
            run_id CHAR(36) COLLATE utf8mb4_unicode_ci, episode INT, steps INT,
            PRIMARY KEY (run_id, episode)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
        self.refresh = ReportingRefresh(self.db)

    def run_row(self, source_id, status='completed', score=10, steps=(10, 20)):
        run_id = str(uuid4())
        self.db.execute("""INSERT INTO simulation_runs VALUES
            (%s, %s, %s, %s, CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))""",
            (source_id, run_id, status, score))
        for episode, moves in enumerate(steps, 1):
            self.db.execute("INSERT INTO simulation_episodes VALUES (%s, %s, %s)",
                            (run_id, episode, moves))
        return run_id

    def event(self, name, process_id=None, content='', event_id=None):
        if event_id is None:
            event_id = self.db.query("SELECT COALESCE(MAX(event_id), 0) + 1 AS id FROM events")[0]['id']
        self.db.execute("""INSERT INTO events (event_id, name, category, log_level, process_id)
            VALUES (%s, %s, 'Configuration', 'INFO', %s)""", (event_id, name, process_id))
        self.db.execute("INSERT INTO event_messages VALUES (%s, %s)", (event_id, content))
        return event_id

    def turn(self, index=0, process_id=None):
        process_id = process_id or str(uuid4())
        self.event('proposal_accepted', process_id)
        return self.event('configuration_compared', process_id)

    def test_backfill_excludes_unfinished_and_unsuccessful_runs_and_is_repeatable(self):
        self.run_row(1, score=11)
        active = self.run_row(2, 'running', score=99, steps=(500,))
        self.run_row(3, 'cancelled', score=80)
        self.run_row(4, 'failed', score=90)
        self.run_row(5, score=None, steps=())
        initial = self.refresh.refresh()
        self.assertEqual(initial, dict(games_played=2, moves_made=30,
            all_time_high_score=11, simulations_submitted=5, experiment_cycles=0))
        self.assertEqual(self.refresh.refresh(), initial)
        # Older IDs that finish later are not lost behind an ID watermark.
        self.db.execute("UPDATE simulation_runs SET status='completed' WHERE run_id=%s", (active,))
        updated = self.refresh.refresh()
        self.assertEqual(updated['games_played'], 3)
        self.assertEqual(updated['moves_made'], 530)
        self.assertEqual(updated['all_time_high_score'], 99)
        source_runs = self.db.query('SELECT * FROM simulation_runs ORDER BY id')
        source_episodes = self.db.query('SELECT * FROM simulation_episodes ORDER BY run_id, episode')
        self.assertEqual(self.refresh.refresh(), updated)
        self.assertEqual(self.refresh.refresh(rebuild=True), updated)
        self.assertEqual(self.db.query('SELECT * FROM simulation_runs ORDER BY id'), source_runs)
        self.assertEqual(self.db.query('SELECT * FROM simulation_episodes ORDER BY run_id, episode'), source_episodes)

    def test_complete_proposals_count_once_across_repeated_events_and_refreshes(self):
        for index in range(8):
            process = str(uuid4())
            self.turn(index, process)
            self.event('configuration_compared', process)
        self.assertEqual(self.refresh.refresh()['experiment_cycles'], 8)
        self.assertEqual(EventLogDb(self.db).experiment_cycles(), 8)
        self.turn()
        self.assertEqual(ReportingRefresh(self.db).refresh()['experiment_cycles'], 9)

    def test_late_visible_comparison_counts_without_an_event_watermark(self):
        self.event('configuration_compared', str(uuid4()), event_id=4)
        self.assertEqual(self.refresh.refresh()['experiment_cycles'], 1)
        self.event('configuration_compared', str(uuid4()), event_id=2)
        self.assertEqual(self.refresh.refresh()['experiment_cycles'], 2)
        self.assertEqual(self.refresh.refresh()['experiment_cycles'], EventLogDb(self.db).experiment_cycles())

    def test_failure_rolls_back_projection_counters_and_progress(self):
        self.run_row(1)
        self.turn(0, str(uuid4()))
        with patch.object(self.refresh._reports, 'save_progress', side_effect=RuntimeError('interrupted')):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                self.refresh.refresh()
        self.assertEqual(self.db.query('SELECT COUNT(*) AS n FROM report_runs')[0]['n'], 0)
        self.assertEqual(self.reports.totals()['games_played'], 0)
        self.assertEqual(self.refresh.refresh()['games_played'], 2)
        self.assertEqual(self.refresh.refresh()['games_played'], 2)

    def test_draft_progress_does_not_change_completed_cycles(self):
        self.event('configuration_draft_saved', str(uuid4()), event_id=1)
        self.event('configuration_compared', str(uuid4()), event_id=4)
        self.assertEqual(self.refresh.refresh()['experiment_cycles'], 1)
        self.event('configuration_draft_saved', str(uuid4()), event_id=3)
        self.assertEqual(self.refresh.refresh()['experiment_cycles'], 1)

    def test_comparison_counts_without_waiting_for_other_events(self):
        process = str(uuid4())
        self.event('configuration_compared', process)
        self.assertEqual(self.refresh.refresh()['experiment_cycles'], 1)
        self.event('proposal_accepted', process)
        self.assertEqual(self.refresh.refresh()['experiment_cycles'], 1)

    def test_incomplete_drafts_do_not_count_as_experiments(self):
        self.run_row(1)
        self.event('configuration_draft_saved', str(uuid4()), content='{}')
        totals = self.refresh.refresh()
        self.assertEqual(totals['experiment_cycles'], 0)
        self.assertEqual(totals['games_played'], 2)

    def test_no_new_runs_does_not_read_episodes_again(self):
        self.run_row(1)
        self.refresh.refresh()
        with patch.object(self.db, 'query', wraps=self.db.query) as query:
            self.refresh.refresh()
        self.assertFalse(any('simulation_episodes' in call.args[0] for call in query.call_args_list))

    def test_backfill_crosses_run_batch_boundaries(self):
        for source_id in range(1, 260):
            self.run_row(source_id, steps=(1,))
        for index in range(520):
            self.turn(index)
        totals = self.refresh.refresh()
        self.assertEqual(totals['games_played'], 259)
        self.assertEqual(totals['moves_made'], 259)
        self.assertEqual(totals['experiment_cycles'], 520)
        self.assertEqual(self.refresh.refresh(), totals)


@unittest.skipUnless(os.environ.get("AX3L_TEST_DB") == "1", "requires disposable MariaDB test database")
class ReportingSerializationTests(unittest.TestCase):
    def test_state_lock_serializes_connections_and_releases_on_rollback(self):
        self.assertEqual(os.environ['DB_NAME'], 'ax3l_test')
        db = DbMgr(initialize_event_tables=False)
        self.addCleanup(db.close)
        ReportingDb(db).initialize()
        started, acquired = Event(), Event()

        def lock_from_another_connection():
            other = DbMgr(initialize_event_tables=False)
            try:
                with other.transaction():
                    started.set()
                    ReportingDb(other).lock_state()
                    acquired.set()
            finally:
                other.close()

        with ThreadPoolExecutor(max_workers=1) as workers:
            with self.assertRaisesRegex(RuntimeError, 'rollback'):
                with db.transaction():
                    ReportingDb(db).lock_state()
                    future = workers.submit(lock_from_another_connection)
                    self.assertTrue(started.wait(2))
                    self.assertFalse(acquired.wait(.1))
                    raise RuntimeError('rollback')
            future.result(timeout=2)
        self.assertTrue(acquired.is_set())
