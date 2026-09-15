import json
import unittest
from unittest.mock import AsyncMock, Mock, patch

from ax3l.constants.DAx3l import DAx3l
from ax3l.app.snakelab.GenerateDefaultConfig import GenerateDefaultConfig
from ax3l.app.snakelab.SeedRotation import rotate_if_needed
from ax3l.constants.DSnakeLab import DSnakeLab


class SeedRotationTests(unittest.IsolatedAsyncioTestCase):
    async def test_threshold_changes_only_seed_and_accepts_lower_baseline(self):
        threshold = DSnakeLab.SEED_STAGNANT_ROUNDS
        for rounds in (threshold - 1, threshold):
            with self.subTest(rounds=rounds), patch('ax3l.app.snakelab.SeedRotation.EventLogDb') as factory:
                events = factory.return_value
                events.pending_seed_rotation.return_value = None
                events.stagnant_rounds.return_value = rounds
                events.current_golden_config.return_value = {'process_id': 'gold'}
                config = GenerateDefaultConfig().run()
                snake, db, wait = Mock(), Mock(), AsyncMock()
                snake.get_config.return_value = config
                snake.get_num_sims.return_value = 12
                snake.find_config_run.return_value = None
                snake.submit_simulation.return_value = 'new'
                snake.get_run_result.return_value = {'status': 'completed', 'high_score': 1}
                run_id = await rotate_if_needed(snake, db, wait)
                if rounds < threshold:
                    self.assertIsNone(run_id)
                    snake.submit_simulation.assert_not_called()
                    wait.assert_not_awaited()
                else:
                    self.assertEqual(run_id, 'new')
                    submission = next(c for c in db.log.call_args_list if c.args[0] == 'simulation_submitted')
                    self.assertEqual(submission.kwargs['ax3l_version'], DAx3l.VERSION)
                    snake.submit_simulation.assert_called_once_with({**config, 'seed': config['seed'] + 1})
                    wait.assert_awaited_once_with(snake, db, 'new')
                    self.assertEqual(db.log.call_args.args[0], 'golden_config_created')
                    self.assertIn('Score to beat: 1', db.log.call_args.args[3])
                    self.assertEqual(db.log.call_args.kwargs['experiment_score'],
                                     {'simulations': 12, 'score': 1, 'seed': config['seed'] + 1})
                    self.assertEqual(config, GenerateDefaultConfig().run())

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
            self.assertEqual(await rotate_if_needed(snake, db, wait), 'recovered')
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
                    await rotate_if_needed(snake, db, wait)
                snake.submit_simulation.assert_not_called()
                self.assertNotIn('golden_config_created', [c.args[0] for c in db.log.call_args_list])

    async def test_startup_defers_new_rotation_until_comparison_recovery(self):
        with patch('ax3l.app.snakelab.SeedRotation.EventLogDb') as factory:
            events = factory.return_value
            events.pending_seed_rotation.return_value = None
            events.stagnant_rounds.return_value = 3
            snake = Mock()
            self.assertIsNone(await rotate_if_needed(snake, Mock(), AsyncMock(), resume_only=True))
            events.stagnant_rounds.assert_not_called()
            snake.submit_simulation.assert_not_called()

    async def test_loop_uses_rotated_baseline_before_next_llm_request(self):
        import asyncio
        from pathlib import Path
        from ax3l.app.Prompt import Prompt
        from ax3l.app.snakelab.SnakeLabLoop import optimize
        module = 'ax3l.app.snakelab.SnakeLabLoop.'
        snake, events = Mock(), Mock()
        snake.is_simulation_running.return_value = False
        snake.get_run_result.return_value = {'status': 'completed', 'high_score': 100}
        events.latest_snakelab_proposal.return_value = None
        events.latest_seed_baseline.return_value = None
        golden = Prompt('gold')
        golden.run_id = 'old'
        rotation = AsyncMock(side_effect=[None, 'rotated'])
        conversation = AsyncMock(side_effect=asyncio.CancelledError())
        with patch(module + 'RoundRobinState') as selector, patch(module + 'SnakeLab', return_value=snake), patch(module + 'EventLogDb', return_value=events), patch(module + 'GoldenConfig', return_value=golden), patch(module + 'rotate_if_needed', rotation), patch(module + 'SnakeLabTools', return_value=AsyncMock()), patch(module + 'converse', conversation), patch(module + 'Comparison', return_value=Prompt('new baseline')) as comparison:
            selector.return_value.begin.return_value = 'hidden_size'
            with self.assertRaises(asyncio.CancelledError):
                await optimize(Mock(), Path('/tmp'), Mock(), 'endpoint')
            comparison.assert_called_once_with('rotated', 'hidden_size')
            prompts = conversation.call_args.args[4]
            self.assertEqual(len(prompts), 2)
            self.assertTrue(all(isinstance(json.loads(p.to_json())['content'], str) for p in prompts))
            self.assertEqual(conversation.call_args.args[4][0].to_md(), 'new baseline')
