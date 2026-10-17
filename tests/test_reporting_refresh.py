"""Reporting backfill, incremental processing, and atomicity on DEV MariaDB.

Use AX3L_TEST_DEV_DB=1 and the disposable ax3l_dev DB_* environment.
Temporary source/projection tables keep fixtures separate from persistent data.
"""

import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch
from uuid import uuid4

from ax3l.activity.CompletedRounds import completed_rounds
from ax3l.app.DbMgr import DbMgr
from ax3l.app.EventLogDb import EventLogDb
from ax3l.app.ReportingDb import ReportingDb
from ax3l.app.ReportingRefresh import ReportingRefresh
from ax3l.app.snakelab.RoundRobinState import ROUND_ROBIN_ORDER
from ax3l.constants.DSnakeLab import DSnakeLab


class CompletedRoundsTests(unittest.TestCase):
    def test_partial_rounds_gaps_and_duplicate_comparisons(self):
        turns = [dict(parameter_index=index, first_completion=first) for index, first in (
            (0, True), (1, True), (1, False), (2, True), (1, True), (0, True))]
        self.assertEqual(completed_rounds(turns, 3), (1, 1))
        self.assertEqual(completed_rounds([
            dict(parameter_index=1, first_completion=True),
            dict(parameter_index=2, first_completion=True)], 3, 1, 1), (2, 0))


@unittest.skipUnless(os.environ.get("AX3L_TEST_DEV_DB") == "1", "requires DEV MariaDB")
class ReportingRefreshTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ["DB_NAME"], "ax3l_dev")
        self.db = DbMgr()
        self.addCleanup(self.db.close)
        self.enterContext(patch.object(DSnakeLab, 'DATABASE', 'ax3l_dev'))
        self.reports = ReportingDb(self.db)
        self.reports.initialize()
        for table in ('report_runs', 'report_events', 'report_turns', 'report_state'):
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

    def turn(self, index, process_id=None, exhausted=False):
        self.event('round_robin_checkpoint', content=json.dumps(
            dict(parameter_order=ROUND_ROBIN_ORDER, index=index)))
        if not exhausted:
            self.event('proposal_accepted', process_id)
        return self.event('parameter_space_exhausted' if exhausted else 'configuration_compared', process_id)

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

    def test_round_count_matches_original_with_duplicates_skips_and_restart(self):
        for index in range(len(ROUND_ROBIN_ORDER)):
            process = str(uuid4())
            self.turn(index, process, exhausted=index % 2 == 0)
            if index % 2:
                self.event('configuration_compared', process)
        self.assertEqual(self.refresh.refresh()['experiment_cycles'], 1)
        self.assertEqual(EventLogDb(self.db).experiment_cycles(), 1)
        # Resume across refresh instances in the middle of a round.
        self.turn(0, str(uuid4()))
        self.assertEqual(self.refresh.refresh()['experiment_cycles'], 1)
        for index in range(1, len(ROUND_ROBIN_ORDER)):
            self.turn(index, str(uuid4()))
        self.assertEqual(ReportingRefresh(self.db).refresh()['experiment_cycles'], 2)
        self.assertEqual(EventLogDb(self.db).experiment_cycles(), 2)

    def test_late_visible_completion_replays_only_projected_turns(self):
        self.event('round_robin_checkpoint', content=json.dumps(
            dict(parameter_order=ROUND_ROBIN_ORDER, index=0)), event_id=1)
        self.event('round_robin_checkpoint', content=json.dumps(
            dict(parameter_order=ROUND_ROBIN_ORDER, index=1)), event_id=3)
        self.event('parameter_space_exhausted', event_id=4)
        self.refresh.refresh()
        self.assertEqual(self.reports.lock_state()['expected_parameter'], 0)
        self.event('parameter_space_exhausted', event_id=2)
        self.refresh.refresh()
        self.assertEqual(self.reports.lock_state()['expected_parameter'], 2)
        self.assertEqual(self.refresh.refresh()['experiment_cycles'], EventLogDb(self.db).experiment_cycles())

    def test_failure_rolls_back_projection_counters_and_progress(self):
        self.run_row(1)
        self.turn(0, str(uuid4()))
        with patch.object(self.refresh._reports, 'save_progress', side_effect=RuntimeError('interrupted')):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                self.refresh.refresh()
        self.assertEqual(self.db.query('SELECT COUNT(*) AS n FROM report_runs')[0]['n'], 0)
        self.assertEqual(self.db.query('SELECT COUNT(*) AS n FROM report_turns')[0]['n'], 0)
        self.assertEqual(self.reports.totals()['games_played'], 0)
        self.assertEqual(self.refresh.refresh()['games_played'], 2)
        self.assertEqual(self.refresh.refresh()['games_played'], 2)

    def test_late_checkpoint_reinterprets_an_already_projected_turn(self):
        self.event('round_robin_checkpoint', content=json.dumps(
            dict(parameter_order=ROUND_ROBIN_ORDER, index=0)), event_id=1)
        self.event('parameter_space_exhausted', event_id=4)
        self.refresh.refresh()
        self.assertEqual(self.reports.lock_state()['expected_parameter'], 1)
        self.event('round_robin_checkpoint', content=json.dumps(
            dict(parameter_order=ROUND_ROBIN_ORDER, index=1)), event_id=3)
        self.refresh.refresh()
        self.assertEqual(self.reports.lock_state()['expected_parameter'], 0)
        self.assertEqual(self.db.query('SELECT parameter_index FROM report_turns')[0]['parameter_index'], 1)

    def test_unresolved_comparison_is_revisited_when_its_proposal_arrives(self):
        self.event('round_robin_checkpoint', content=json.dumps(
            dict(parameter_order=ROUND_ROBIN_ORDER, index=0)))
        process = str(uuid4())
        self.event('configuration_compared', process)
        self.refresh.refresh()
        self.assertEqual(self.reports.lock_state()['expected_parameter'], 0)
        self.event('proposal_accepted', process)
        self.refresh.refresh()
        self.assertEqual(self.reports.lock_state()['expected_parameter'], 1)
        self.assertEqual(self.refresh.refresh()['experiment_cycles'], EventLogDb(self.db).experiment_cycles())

    def test_invalid_checkpoint_rolls_back_backfill(self):
        self.run_row(1)
        self.event('round_robin_checkpoint', content=json.dumps(dict(parameter_order=['changed'], index=0)))
        self.event('parameter_space_exhausted')
        with self.assertRaisesRegex(ValueError, 'Search parameter order changed'):
            self.refresh.refresh()
        self.assertEqual(self.db.query('SELECT COUNT(*) AS n FROM report_runs')[0]['n'], 0)

    def test_no_new_runs_does_not_read_episodes_again(self):
        self.run_row(1)
        self.refresh.refresh()
        with patch.object(self.db, 'query', wraps=self.db.query) as query:
            self.refresh.refresh()
        self.assertFalse(any('simulation_episodes' in call.args[0] for call in query.call_args_list))

    def test_backfill_crosses_run_and_event_batch_boundaries(self):
        for source_id in range(1, 260):
            self.run_row(source_id, steps=(1,))
        for index in range(520):
            self.turn(index % len(ROUND_ROBIN_ORDER), exhausted=True)
        totals = self.refresh.refresh()
        self.assertEqual(totals['games_played'], 259)
        self.assertEqual(totals['moves_made'], 259)
        self.assertEqual(totals['experiment_cycles'], 520 // len(ROUND_ROBIN_ORDER))
        self.assertEqual(self.refresh.refresh(), totals)


@unittest.skipUnless(os.environ.get("AX3L_TEST_DEV_DB") == "1", "requires DEV MariaDB")
class ReportingSerializationTests(unittest.TestCase):
    def test_state_lock_serializes_connections_and_releases_on_rollback(self):
        self.assertEqual(os.environ['DB_NAME'], 'ax3l_dev')
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
