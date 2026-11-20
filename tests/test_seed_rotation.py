import json
from copy import deepcopy
import os
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from ax3l.app.ConfigurationLog import ConfigurationLog
from ax3l.app.DbMgr import DbMgr
from ax3l.app.EventLogDb import EventLogDb
from ax3l.app.snakelab.ExperimentDb import ExperimentDb
from ax3l.app.snakelab.GenerateDefaultConfig import GenerateDefaultConfig
from ax3l.app.snakelab.SeedRotation import resume_seed_rotation, rotate_draft_seed
from ax3l.entities.ConfigurationDraft import ConfigurationDraft


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


class DraftSeedRotationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = GenerateDefaultConfig().run()
        self.baseline = {**deepcopy(self.config), 'seed': self.config['seed'] + 1}
        self.draft = ConfigurationDraft('draft', 'gold', {'golden': 'gold'}, deepcopy(self.baseline),
                                        ['seed'], 'ready')
        self.snake, self.db, self.experiments, self.wait = Mock(), Mock(), Mock(), AsyncMock()
        self.db.log.return_value = 12
        self.snake.submit_simulation.return_value = 'baseline'
        self.snake.find_config_run.return_value = 'baseline'
        self.snake.get_run_result.side_effect = lambda run_id: dict(
            config=self.config if run_id == 'gold' else self.baseline,
            status='completed', high_score=30 if run_id == 'gold' else 0)
        self.snake.get_num_sims.return_value = 3
        self.events = self.enterContext(patch('ax3l.app.snakelab.SeedRotation.EventLogDb')).return_value
        self.events.seed_rotation.return_value = None
        self.rotation = dict(event_id=10, submitted_event_id=11, completed_event_id=None,
                             run_id='baseline', content=json.dumps(dict(draft_id='draft', config=self.baseline)),
                             ax3l_version='test-version')

    async def rotate(self):
        await rotate_draft_seed(self.snake, self.db, self.experiments, self.draft, self.wait)

    async def test_seed_only_rotation_accepts_zero_without_comparing_or_changing_other_values(self):
        await self.rotate()
        self.snake.submit_simulation.assert_called_once_with(self.baseline)
        self.wait.assert_awaited_once_with(self.snake, self.db, 'baseline')
        self.assertEqual(self.draft.run_id, 'baseline')
        self.assertEqual(self.draft.golden_run_id, 'baseline')
        self.assertEqual(self.draft.phase, 'submitted')
        self.assertEqual(self.db.log.call_args.kwargs['experiment_score'], dict(simulations=3, score=0, seed=1971))

    async def test_other_changes_stay_staged_until_baseline_completion(self):
        self.draft.config['model']['layers'] += 1
        requested = deepcopy(self.draft.config)

        async def wait(*args):
            self.assertEqual(self.draft.phase, 'rotating_seed')
            self.assertEqual(self.draft.golden_run_id, 'gold')
            self.assertEqual(self.draft.config, requested)

        self.wait.side_effect = wait
        await self.rotate()
        self.snake.submit_simulation.assert_called_once_with(self.baseline)
        self.assertEqual(self.draft.config, requested)
        self.assertEqual(self.draft.phase, 'ready')
        self.assertEqual(self.draft.golden_run_id, 'baseline')
        self.assertIsNone(self.draft.run_id)

    async def test_restart_reconciles_a_lost_baseline_reply_without_resubmitting(self):
        self.events.seed_rotation.side_effect = [None, {**self.rotation, 'run_id': None, 'submitted_event_id': None}]
        self.snake.submit_simulation.side_effect = TimeoutError('lost reply')
        with self.assertRaises(TimeoutError):
            await self.rotate()
        self.assertEqual(self.draft.phase, 'rotating_seed')
        await self.rotate()
        self.snake.submit_simulation.assert_called_once()
        self.snake.find_config_run.assert_called_once_with(self.baseline)
        self.wait.assert_awaited_once_with(self.snake, self.db, 'baseline')
        self.assertEqual(self.draft.run_id, 'baseline')

    async def test_unresolved_baseline_submission_stops_without_retrying(self):
        self.events.seed_rotation.return_value = {**self.rotation, 'run_id': None, 'submitted_event_id': None}
        self.snake.find_config_run.return_value = None
        with self.assertRaisesRegex(RuntimeError, 'submission is unresolved'):
            await self.rotate()
        self.snake.submit_simulation.assert_not_called()
        self.wait.assert_not_awaited()
        self.db.log.assert_not_called()

    async def test_restart_monitors_the_recorded_baseline(self):
        self.events.seed_rotation.return_value = self.rotation
        await self.rotate()
        self.snake.submit_simulation.assert_not_called()
        self.snake.find_config_run.assert_not_called()
        self.wait.assert_awaited_once_with(self.snake, self.db, 'baseline')

    async def test_restart_after_promotion_recovers_draft_without_repeating_the_baseline_or_snapshot(self):
        for other_changes in (False, True):
            with self.subTest(other_changes=other_changes):
                self.draft = ConfigurationDraft('draft', 'gold', {'golden': 'gold'}, deepcopy(self.baseline),
                                                ['seed'], 'rotating_seed')
                if other_changes:
                    self.draft.config['model']['layers'] += 1
                self.events.seed_rotation.return_value = {**self.rotation, 'completed_event_id': 13}
                await self.rotate()
                self.assertEqual(self.draft.golden_run_id, 'baseline')
                self.assertEqual(self.draft.phase, 'ready' if other_changes else 'submitted')
        self.snake.submit_simulation.assert_not_called()
        self.wait.assert_not_awaited()
        self.db.log.assert_not_called()

    async def test_incomplete_baseline_cannot_become_golden(self):
        self.events.seed_rotation.return_value = self.rotation
        self.snake.get_run_result.side_effect = lambda run_id: dict(
            config=self.config, status='completed', high_score=None)
        with self.assertRaisesRegex(ValueError, 'completed simulation with a recorded high score'):
            await self.rotate()
        self.assertEqual(self.draft.golden_run_id, 'gold')
        self.db.log.assert_not_called()


@unittest.skipUnless(os.environ.get('AX3L_TEST_DB') == '1', 'requires disposable MariaDB test database')
class SeedRotationDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_restart_after_baseline_acceptance_does_not_repeat_run_or_score_snapshot(self):
        self.assertEqual(os.environ['DB_NAME'], 'ax3l_test')
        db = DbMgr()
        self.addCleanup(db.close)
        first_event = db.query('SELECT COALESCE(MAX(event_id), 0) AS id FROM events')[0]['id']

        def cleanup():
            db.execute('UPDATE events SET parent_event_id=NULL WHERE event_id>%s', (first_event,))
            db.execute('DELETE FROM events WHERE event_id>%s', (first_event,))

        self.addCleanup(cleanup)
        config = GenerateDefaultConfig().run()
        baseline = {**deepcopy(config), 'seed': config['seed'] + 1}
        gold_id, baseline_id, draft_id = [str(uuid4()) for _ in range(3)]
        ConfigurationLog(db).golden_config_created(gold_id, reason='Initial baseline',
            experiment_score=dict(simulations=1, score=30, seed=config['seed']))
        experiments = ExperimentDb(db)
        draft = ConfigurationDraft(draft_id, gold_id, {'golden': gold_id}, deepcopy(baseline), ['seed'], 'ready')
        experiments.save_draft(draft)
        snake, wait = Mock(), AsyncMock()
        snake.submit_simulation.return_value = baseline_id
        snake.get_run_result.side_effect = lambda run_id: dict(
            config=config if run_id == gold_id else baseline,
            status='completed', high_score=30 if run_id == gold_id else 0)
        snake.get_num_sims.return_value = 2
        original_save = experiments.save_draft

        def stop_before_draft_update(saved):
            if saved.golden_run_id == baseline_id:
                raise RuntimeError('interrupted after promotion')
            original_save(saved)

        with patch.object(experiments, 'save_draft', side_effect=stop_before_draft_update):
            with self.assertRaisesRegex(RuntimeError, 'interrupted after promotion'):
                await rotate_draft_seed(snake, db, experiments, draft, wait)
        self.assertEqual(experiments.draft().phase, 'rotating_seed')
        self.assertEqual(EventLogDb(db).current_golden_config()['process_id'], baseline_id)
        self.assertIsNone(EventLogDb(db).pending_seed_rotation())
        restarted = DbMgr()
        self.addCleanup(restarted.close)
        recovered = ExperimentDb(restarted).draft()
        await rotate_draft_seed(snake, restarted, ExperimentDb(restarted), recovered, wait)
        snake.submit_simulation.assert_called_once_with(baseline)
        wait.assert_awaited_once_with(snake, db, baseline_id)
        saved = ExperimentDb(restarted).draft()
        self.assertEqual(saved.run_id, baseline_id)
        self.assertEqual(saved.golden_run_id, baseline_id)
        self.assertEqual(saved.phase, 'submitted')
        self.assertEqual([(row['score'], row['seed']) for row in EventLogDb(restarted).experiment_highscores()],
                         [(30, config['seed']), (0, baseline['seed'])])
