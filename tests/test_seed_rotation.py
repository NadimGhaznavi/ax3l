"""System-owned seed rotation after sixteen consecutive strictly lower scores."""

from copy import deepcopy
import json
from unittest.mock import Mock, patch

from ax3l.entities.ExperimentView import VIEWS
from ax3l.interface.SimulationConfiguration import SimulationConfiguration
from ax3l.interface.ViewConversation import ViewConversation
from experiment_fixture import ExperimentFixture
from test_view_experiments import prompt_text
from view_cycle_fixtures import FakeSnake, MemoryLog


class SeedRotationTests(ExperimentFixture):
    def test_sixteen_losses_trigger_new_golden_baseline_before_next_selection(self):
        self.snake = FakeSnake((10,) + (9,) * 16 + (4, 5))
        self.loop().run(cycles=16)
        self.assertEqual(len(self.snake.submissions), 17)
        state = self.store.load()
        self.assertEqual(state.failures, 16)
        old_golden = state.golden_run_id
        self.loop().run(cycles=1)
        self.assertEqual(len(self.snake.submissions), 19)
        baseline, candidate = self.snake.submissions[-2:]
        expected = deepcopy(self.snake.results[old_golden]['config'])
        expected['seed'] += 1
        self.assertEqual(baseline, expected)
        self.assertEqual(candidate['seed'], baseline['seed'])
        state = self.store.load()
        self.assertEqual(state.reference_run_id, list(self.snake.results)[-2])
        self.assertEqual(state.golden_run_id, state.run_id)
        self.assertEqual(state.failures, 0)
        self.assertIn('Baseline Results', prompt_text(self.model.requests[-2]))
        self.assertEqual(self.event_count('configuration_compared'), 17)
        self.assertEqual(self.event_count('golden_config_created'), 3)

    def test_tie_or_improvement_restarts_the_full_sixteen_loss_count(self):
        for score in (10, 11):
            with self.subTest(score=score):
                self.log.events.clear()
                self.store.state = None
                self.model.requests.clear()
                self.snake = FakeSnake((10,) + (9,) * 15 + (score,) + (9,) * 15)
                self.loop().run(cycles=31)
                self.assertEqual(self.store.load().failures, 15)
                self.assertTrue(all(config['seed'] == SimulationConfiguration.defaults()['seed']
                                    for config in self.snake.submissions))
                self.assertEqual(self.event_count('golden_config_created'), 2)

    def at_rotation(self):
        self.loop().run(cycles=1)
        state = self.store.load()
        state.failures = 16
        self.store.save(state)
        return state

    def test_lost_seed_baseline_reply_reconciles_without_resubmission(self):
        self.at_rotation()
        self.snake.scores = iter((4, 5))
        submit = self.snake.submit_simulation
        def lost(config):
            submit(config)
            raise TimeoutError('Lost reply')
        with patch.object(self.snake, 'submit_simulation', side_effect=lost):
            with self.assertRaises(TimeoutError):
                self.loop().run(cycles=1)
        self.assertTrue(self.store.load().seed_baseline)
        self.assertEqual(self.store.load().phase, 'submitting')
        self.loop().run(cycles=1)
        self.assertEqual(len(self.snake.submissions), 4)
        self.assertEqual(self.snake.submissions[-1]['seed'], self.snake.submissions[-2]['seed'])
        self.assertEqual(self.store.load().failures, 0)

    def test_rotation_restart_clears_history_and_does_not_skip_the_pending_view(self):
        self.snake = FakeSnake((10, 11, 4, 3))
        old = self.at_rotation()
        self.assertIsNotNone(old.golden_history)
        save = self.store.save
        def stop(state):
            if state.seed_baseline and state.phase == 'completed':
                raise KeyboardInterrupt()
            save(state)
        with patch.object(self.store, 'save', side_effect=stop):
            with self.assertRaises(KeyboardInterrupt):
                self.loop().run(cycles=1)
        self.assertEqual(self.store.load().phase, 'comparing')
        self.loop().run(cycles=1)
        state = self.store.load()
        self.assertEqual(state.view_index, old.view_index + 1)
        self.assertIsNone(state.golden_history)
        self.assertEqual(state.failures, 1)
        self.assertEqual(len(self.snake.submissions), 4)
        self.assertEqual(self.event_count('golden_config_created'), 3)
        self.assertIn('Baseline Results', prompt_text(self.model.requests[-2]))

    def test_failed_seed_baseline_blocks_new_selection_until_resolved(self):
        self.at_rotation()
        submit = self.snake.submit_simulation
        def failed(config):
            run_id = submit(config)
            self.snake.results[run_id]['status'] = 'failed'
            return run_id
        with patch.object(self.snake, 'submit_simulation', side_effect=failed):
            with self.assertRaisesRegex(RuntimeError, 'failed'):
                self.loop().run(cycles=1)
        self.assertEqual(len(self.model.requests), 2)
        state = self.store.load()
        self.assertTrue(state.seed_baseline)
        self.snake.results[state.run_id]['status'] = 'completed'
        self.loop().run(cycles=1)
        self.assertEqual(len(self.snake.submissions), 4)

    def test_seed_changes_are_rejected_with_feedback_before_accepting_valid_values(self):
        for values in ({'new seed': True}, {'seed': 1971}):
            llm = Mock(url='http://fixture')
            arguments = json.dumps(dict(hypothesis='Change the seed.', values=values))
            response = dict(choices=[dict(message=dict(tool_calls=[dict(id='proposal', function=dict(
                name='submit_view', arguments=arguments))]))])
            corrected = deepcopy(response)
            corrected['choices'][0]['message']['tool_calls'][0]['function']['arguments'] = json.dumps(
                dict(hypothesis='Keep the seed.', values={'training.gamma': .95}))
            llm.complete.side_effect = [(200, '', json.dumps(reply).encode()) for reply in (response, corrected)]
            result = ViewConversation(llm, MemoryLog()).propose(VIEWS['training'], 'Tune.', 'seed-test')
            self.assertEqual(result.values, {'training.gamma': .95})
            self.assertEqual(llm.complete.call_count, 2)
            feedback = json.loads(llm.complete.call_args.args[0])['messages'][-1]
            self.assertIn('## Rejected proposal', feedback['content'])
