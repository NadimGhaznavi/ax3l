import json
import unittest
from unittest.mock import AsyncMock, Mock, patch

from ax3l.app.snakelab.GenerateDefaultConfig import GenerateDefaultConfig
from ax3l.app.snakelab.SeedRotation import resume_seed_rotation


class SeedRotationTests(unittest.IsolatedAsyncioTestCase):
    async def test_stagnation_never_starts_an_automatic_rotation(self):
        for rounds in (0, 8, 9, 100):
            with self.subTest(rounds=rounds), patch('ax3l.app.snakelab.SeedRotation.EventLogDb') as factory:
                events = factory.return_value
                events.pending_seed_rotation.return_value = None
                events.stagnant_rounds.return_value = rounds
                snake, db, wait = Mock(), Mock(), AsyncMock()
                self.assertIsNone(await resume_seed_rotation(snake, db, wait))
                events.stagnant_rounds.assert_not_called()
                snake.submit_simulation.assert_not_called()
                wait.assert_not_awaited()
                db.log.assert_not_called()

    async def test_restart_reconciles_submission_without_resubmitting(self):
        with patch('ax3l.app.snakelab.SeedRotation.EventLogDb') as factory:
            config = GenerateDefaultConfig().run()
            config['seed'] += 1
            factory.return_value.pending_seed_rotation.return_value = {
                'event_id': 2, 'run_id': None, 'submitted_event_id': None,
                'content': json.dumps({'config': config}), 'ax3l_version': '0.9.0'}
            snake, db, wait = Mock(), Mock(), AsyncMock()
            snake.find_config_run.return_value = 'recovered'
            snake.get_run_result.return_value = {'status': 'completed', 'high_score': 0}
            self.assertEqual(await resume_seed_rotation(snake, db, wait), 'recovered')
            snake.submit_simulation.assert_not_called()
            wait.assert_awaited_once_with(snake, db, 'recovered')
            submission = next(c for c in db.log.call_args_list if c.args[0] == 'simulation_submitted')
            self.assertEqual(submission.kwargs['ax3l_version'], '0.9.0')

    async def test_unknown_submission_or_failed_baseline_does_not_promote(self):
        for found in (None, 'failed'):
            with self.subTest(found=found), patch('ax3l.app.snakelab.SeedRotation.EventLogDb') as factory:
                factory.return_value.pending_seed_rotation.return_value = {
                    'event_id': 2, 'run_id': None, 'submitted_event_id': None,
                    'content': json.dumps({'config': GenerateDefaultConfig().run()})}
                snake, db, wait = Mock(), Mock(), AsyncMock()
                snake.find_config_run.return_value = found
                wait.side_effect = RuntimeError('failed')
                with self.assertRaises(RuntimeError):
                    await resume_seed_rotation(snake, db, wait)
                snake.submit_simulation.assert_not_called()
                self.assertNotIn('golden_config_created', [c.args[0] for c in db.log.call_args_list])

    async def test_recorded_rotation_completes_its_original_baseline_before_new_work(self):
        with patch('ax3l.app.snakelab.SeedRotation.EventLogDb') as factory:
            events = factory.return_value
            config = GenerateDefaultConfig().run()
            config['seed'] += 1
            events.pending_seed_rotation.return_value = {
                'event_id': 2, 'run_id': 'submitted', 'submitted_event_id': 3,
                'content': json.dumps({'config': config})}
            snake, db, wait = Mock(), Mock(), AsyncMock()
            snake.get_run_result.return_value = dict(status='completed', high_score=1)
            snake.get_num_sims.return_value = 12
            self.assertEqual(await resume_seed_rotation(snake, db, wait), 'submitted')
            snake.submit_simulation.assert_not_called()
            wait.assert_awaited_once_with(snake, db, 'submitted')
            self.assertEqual(db.log.call_args.kwargs['experiment_score'],
                             dict(simulations=12, score=1, seed=config['seed']))
            events.stagnant_rounds.assert_not_called()
