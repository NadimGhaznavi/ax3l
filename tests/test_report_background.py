"""Cache freshness, failure handling, and independent background report work."""

from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch
from uuid import uuid4

import pymysql

from ax3l.app.ReportBackground import ReportBackground
from ax3l.interface.SimulationGifStore import SimulationGifStore


class ReportBackgroundTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.snake = self.enterContext(patch('ax3l.app.ReportBackground.SnakeLab')).return_value
        self.db = self.enterContext(patch('ax3l.app.ReportBackground.DbMgr')).return_value
        self.refresh = self.enterContext(patch('ax3l.app.ReportBackground.ReportingRefresh')).return_value
        self.clock = self.enterContext(patch('ax3l.app.ReportBackground.monotonic', return_value=10))
        self.background = ReportBackground(SimulationGifStore(Path(directory), 2, 20), 20)
        self.addCleanup(self.background.close)

    def finish_totals(self):
        self.background._totals_job.result(timeout=2)

    def test_totals_initial_load_fresh_cache_and_stale_refresh(self):
        started, release = Event(), Event()
        self.addCleanup(release.set)

        def initial(**kwargs):
            started.set()
            if not release.wait(3):
                raise TimeoutError('Test did not release totals')
            return {'games_played': 100, 'moves_made': 2000}

        self.refresh.refresh.side_effect = initial
        self.assertEqual(self.background.episode_totals(), {'games_played': None, 'moves_made': None})
        self.assertTrue(started.wait(1))
        for _ in range(5):
            self.assertIsNone(self.background.episode_totals()['games_played'])
        self.refresh.refresh.assert_called_once_with(initialize=True)
        release.set()
        self.finish_totals()
        self.assertEqual(self.background.episode_totals()['games_played'], 100)
        returned = self.background.episode_totals()
        returned['games_played'] = 999
        self.assertEqual(self.background.episode_totals()['games_played'], 100)
        self.clock.return_value = 69
        self.background.episode_totals()
        self.refresh.refresh.assert_called_once_with(initialize=True)

        # Readers retain the successful snapshot while an expired cache refreshes.
        started.clear()
        release.clear()
        self.clock.return_value = 70
        self.refresh.refresh.side_effect = initial
        self.assertEqual(self.background.episode_totals()['moves_made'], 2000)
        self.assertTrue(started.wait(1))
        self.assertEqual(self.background.episode_totals()['games_played'], 100)
        self.assertEqual(self.refresh.refresh.call_count, 2)
        release.set()
        self.finish_totals()
        self.background.episode_totals()

    def test_failed_refresh_preserves_last_result_and_waits_before_retry(self):
        self.refresh.refresh.return_value = {'games_played': 5, 'moves_made': 50}
        self.background.episode_totals()
        self.finish_totals()
        self.assertEqual(self.background.episode_totals()['games_played'], 5)
        self.clock.return_value = 70
        self.refresh.refresh.side_effect = pymysql.OperationalError('DB offline')
        with self.assertLogs(level='ERROR'):
            self.assertEqual(self.background.episode_totals()['games_played'], 5)
            self.finish_totals()
        self.assertEqual(self.background.episode_totals()['games_played'], 5)
        self.clock.return_value = 129
        self.background.episode_totals()
        self.assertEqual(self.refresh.refresh.call_count, 2)
        self.clock.return_value = 130
        self.refresh.refresh.side_effect = None
        self.refresh.refresh.return_value = {'games_played': 6, 'moves_made': 60}
        self.background.episode_totals()
        self.finish_totals()
        self.assertEqual(self.background.episode_totals(), {'games_played': 6, 'moves_made': 60})

    def test_programming_errors_are_not_hidden_by_cached_totals(self):
        self.refresh.refresh.side_effect = ValueError('invalid internal result')
        self.background.episode_totals()
        with self.assertRaisesRegex(ValueError, 'invalid internal result'):
            self.finish_totals()
        with self.assertRaisesRegex(ValueError, 'invalid internal result'):
            self.background.episode_totals()

    def test_missing_capture_deduplicates_and_retries_after_one_minute(self):
        run_id = str(uuid4())
        self.snake.get_highscore_frames.return_value = None
        self.assertFalse(self.background.animation_ready(run_id, 123))
        self.background._gif_jobs[run_id].result(timeout=2)
        for _ in range(5):
            self.assertFalse(self.background.animation_ready(run_id, 123))
        self.snake.get_highscore_frames.assert_called_once_with(run_id)
        self.clock.return_value = 70
        self.assertFalse(self.background.animation_ready(run_id, 123))
        self.background._gif_jobs[run_id].result(timeout=2)
        self.assertEqual(self.snake.get_highscore_frames.call_count, 2)

    def test_control_status_does_not_wait_for_reporting_backfill(self):
        started, release = Event(), Event()
        self.addCleanup(release.set)

        def refresh(**kwargs):
            started.set()
            if not release.wait(3):
                raise TimeoutError('Test did not release summary refresh')
            return dict(games_played=1000, moves_made=2000, experiment_cycles=45,
                        simulations_submitted=100, all_time_high_score=12)

        self.refresh.refresh.side_effect = refresh
        self.snake.is_simulation_running.return_value = False
        self.assertIsNone(self.background.status()['experiment_cycles'])
        self.assertTrue(started.wait(1))
        self.background._status_job.result(timeout=2)
        self.assertEqual(self.background.status()['snake_lab_status'], 'Idle')
        self.assertIsNone(self.background.status()['experiment_cycles'])
        self.refresh.refresh.assert_called_once_with(initialize=True)
        release.set()
        self.finish_totals()
        self.assertEqual(self.background.status(), dict(experiment_cycles=45,
            simulations_submitted=100, all_time_high_score=12, snake_lab_status='Idle'))
        self.db.close.assert_called_once_with()
        self.clock.return_value = 69
        self.background.status()
        self.refresh.refresh.assert_called_once_with(initialize=True)
        self.snake.get_episode_totals.assert_not_called()
        self.snake.get_high_score.assert_not_called()
        self.snake.get_num_sims.assert_not_called()

    def test_status_database_failure_retains_previous_summary(self):
        self.refresh.refresh.return_value = dict(games_played=5, moves_made=50,
            experiment_cycles=10, simulations_submitted=50, all_time_high_score=5)
        self.snake.is_simulation_running.return_value = True
        self.background.status()
        self.finish_totals()
        self.background._status_job.result(timeout=2)
        previous = self.background.status()
        self.clock.return_value = 70
        self.refresh.refresh.side_effect = pymysql.OperationalError('offline')
        with self.assertLogs(level='ERROR'):
            self.background.status()
            self.finish_totals()
        self.assertEqual(self.background.status(), previous)
        self.assertEqual(self.db.close.call_count, 2)
        self.refresh.refresh.assert_called_with(initialize=False)
