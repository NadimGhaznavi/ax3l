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
        self.log = self.enterContext(patch('ax3l.app.ReportBackground.EventLogDb')).return_value
        self.clock = self.enterContext(patch('ax3l.app.ReportBackground.monotonic', return_value=10))
        self.background = ReportBackground(SimulationGifStore(Path(directory), 2, 20), 20)
        self.addCleanup(self.background.close)

    def finish_totals(self):
        self.background._totals_job.result(timeout=2)

    def test_totals_initial_load_fresh_cache_and_stale_refresh(self):
        started, release = Event(), Event()
        self.addCleanup(release.set)

        def initial():
            started.set()
            if not release.wait(3):
                raise TimeoutError('Test did not release totals')
            return {'games_played': 100, 'moves_made': 2000}

        self.snake.get_episode_totals.side_effect = initial
        self.assertEqual(self.background.episode_totals(), {'games_played': None, 'moves_made': None})
        self.assertTrue(started.wait(1))
        for _ in range(5):
            self.assertIsNone(self.background.episode_totals()['games_played'])
        self.snake.get_episode_totals.assert_called_once_with()
        release.set()
        self.finish_totals()
        self.assertEqual(self.background.episode_totals()['games_played'], 100)
        returned = self.background.episode_totals()
        returned['games_played'] = 999
        self.assertEqual(self.background.episode_totals()['games_played'], 100)
        self.clock.return_value = 69
        self.background.episode_totals()
        self.snake.get_episode_totals.assert_called_once_with()

        # Readers retain the successful snapshot while an expired cache refreshes.
        started.clear()
        release.clear()
        self.clock.return_value = 70
        self.snake.get_episode_totals.side_effect = initial
        self.assertEqual(self.background.episode_totals()['moves_made'], 2000)
        self.assertTrue(started.wait(1))
        self.assertEqual(self.background.episode_totals()['games_played'], 100)
        self.assertEqual(self.snake.get_episode_totals.call_count, 2)
        release.set()
        self.finish_totals()
        self.background.episode_totals()

    def test_failed_refresh_preserves_last_result_and_waits_before_retry(self):
        self.snake.get_episode_totals.return_value = {'games_played': 5, 'moves_made': 50}
        self.background.episode_totals()
        self.finish_totals()
        self.assertEqual(self.background.episode_totals()['games_played'], 5)
        self.clock.return_value = 70
        self.snake.get_episode_totals.side_effect = pymysql.OperationalError('DB offline')
        with self.assertLogs(level='ERROR'):
            self.assertEqual(self.background.episode_totals()['games_played'], 5)
            self.finish_totals()
        self.assertEqual(self.background.episode_totals()['games_played'], 5)
        self.clock.return_value = 129
        self.background.episode_totals()
        self.assertEqual(self.snake.get_episode_totals.call_count, 2)
        self.clock.return_value = 130
        self.snake.get_episode_totals.side_effect = None
        self.snake.get_episode_totals.return_value = {'games_played': 6, 'moves_made': 60}
        self.background.episode_totals()
        self.finish_totals()
        self.assertEqual(self.background.episode_totals(), {'games_played': 6, 'moves_made': 60})

    def test_programming_errors_are_not_hidden_by_cached_totals(self):
        self.snake.get_episode_totals.side_effect = ValueError('invalid internal result')
        self.background.episode_totals()
        with self.assertRaisesRegex(ValueError, 'invalid internal result'):
            self.finish_totals()
        with self.assertRaisesRegex(ValueError, 'invalid internal result'):
            self.background.episode_totals()

    def test_missing_capture_deduplicates_and_retries_after_one_minute(self):
        run_id = str(uuid4())
        self.snake.get_highscore_frames.return_value = None
        self.assertFalse(self.background.animation_ready(run_id))
        self.background._gif_jobs[run_id].result(timeout=2)
        for _ in range(5):
            self.assertFalse(self.background.animation_ready(run_id))
        self.snake.get_highscore_frames.assert_called_once_with(run_id)
        self.clock.return_value = 70
        self.assertFalse(self.background.animation_ready(run_id))
        self.background._gif_jobs[run_id].result(timeout=2)
        self.assertEqual(self.snake.get_highscore_frames.call_count, 2)

    def test_status_does_not_wait_for_slow_completed_experiments(self):
        started, release = Event(), Event()
        self.addCleanup(release.set)

        def cycles():
            started.set()
            if not release.wait(3):
                raise TimeoutError('Test did not release cycles query')
            return 45

        self.log.experiment_cycles.side_effect = cycles
        self.snake.is_simulation_running.return_value = False
        self.snake.get_high_score.return_value = 12
        self.snake.get_num_sims.return_value = 100
        self.assertIsNone(self.background.status()['experiment_cycles'])
        self.assertTrue(started.wait(1))
        for _ in range(5):
            self.assertEqual(self.background.status()['snake_lab_status'], 'Loading')
        self.log.experiment_cycles.assert_called_once_with()
        release.set()
        self.background._status_job.result(timeout=2)
        self.assertEqual(self.background.status(), dict(experiment_cycles=45,
            simulations_submitted=100, all_time_high_score=12, snake_lab_status='Idle'))
        self.db.close.assert_called_once_with()
        self.clock.return_value = 69
        self.background.status()
        self.log.experiment_cycles.assert_called_once_with()

    def test_status_database_failure_retains_previous_snapshot(self):
        self.log.experiment_cycles.return_value = 10
        self.snake.is_simulation_running.return_value = True
        self.snake.get_high_score.return_value = 5
        self.snake.get_num_sims.return_value = 50
        self.background.status()
        self.background._status_job.result(timeout=2)
        previous = self.background.status()
        self.clock.return_value = 70
        self.log.experiment_cycles.side_effect = pymysql.OperationalError('offline')
        with self.assertLogs(level='ERROR'):
            self.background.status()
            self.background._status_job.result(timeout=2)
        self.assertEqual(self.background.status(), previous)
        self.assertEqual(self.db.close.call_count, 2)
