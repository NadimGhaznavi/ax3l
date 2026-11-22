"""Only Qwen's explicit decision makes a checked unique draft ready to submit."""

from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

from ax3l.app.snakelab.RunSimulationHandler import RunSimulationHandler
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


class RunSimulationHandlerTests(unittest.TestCase):
    def setUp(self):
        self.store = self.enterContext(patch('ax3l.app.snakelab.RunSimulationHandler.ExperimentDb')).return_value
        self.snake = self.enterContext(patch('ax3l.app.snakelab.SubmitSingleValueHandler.SnakeLab')).return_value
        self.snake.is_config_unique.return_value = True
        self.draft = ConfigurationDraft('draft', 'gold', {}, SimulationConfiguration.defaults(),
                                        ['gamma'], 'reviewing')
        self.store.draft.return_value = self.draft
        self.handler = RunSimulationHandler(Mock())

    def test_run_decision_is_saved_without_submitting_or_changing_values(self):
        original = deepcopy(self.draft.config)
        result = self.handler.submit(dict(draft_id='draft'))
        self.assertEqual(result, dict(status='ok', draft_id='draft', phase='ready'))
        self.assertEqual(self.draft.config, original)
        self.snake.is_config_unique.assert_called_once_with(original)
        self.store.save_draft.assert_called_once_with(self.draft)
        self.snake.submit_simulation.assert_not_called()

    def test_inactive_and_stale_drafts_cannot_run(self):
        for phase in ('preparing', 'ready', 'submitting', 'submitted', 'completed', 'failed', 'rotating_seed'):
            self.draft.phase = phase
            self.assertEqual(self.handler.submit(dict(draft_id='draft'))['status'], 'rejected')
        self.draft.phase = 'reviewing'
        self.assertEqual(self.handler.submit(dict(draft_id='old'))['status'], 'rejected')
        self.store.draft.return_value = None
        self.assertEqual(self.handler.submit(dict(draft_id='draft'))['status'], 'rejected')
        self.store.save_draft.assert_not_called()
        self.snake.is_config_unique.assert_not_called()
        self.snake.submit_simulation.assert_not_called()

    def test_duplicate_configurations_are_rejected_on_every_setup_screen(self):
        self.snake.is_config_unique.return_value = False
        for phase in ('selecting_parameter', 'choosing', 'reviewing'):
            with self.subTest(phase=phase):
                self.draft.phase = phase
                self.draft.parameter = 'layers' if phase == 'choosing' else None
                self.draft.selections = [] if phase == 'selecting_parameter' else ['gamma']
                original = deepcopy(self.draft)
                result = self.handler.submit(dict(draft_id='draft'))
                self.assertEqual(result['status'], 'rejected')
                self.assertEqual(result['code'], 'duplicate_configuration')
                self.assertIn('configuration already exists', result['prompt']['content'])
                self.assertNotIn('Submit a legal value', result['prompt']['content'])
                self.assertEqual(self.draft, original)
        self.assertEqual(self.snake.is_config_unique.call_count, 3)
        self.store.save_draft.assert_not_called()
        self.snake.submit_simulation.assert_not_called()

    def test_unique_saved_configuration_can_run_from_every_setup_screen(self):
        for phase in ('selecting_parameter', 'choosing', 'reviewing'):
            with self.subTest(phase=phase):
                self.draft.phase = phase
                self.draft.parameter = 'layers' if phase == 'choosing' else None
                self.draft.selections = [] if phase == 'selecting_parameter' else ['gamma']
                original = deepcopy(self.draft)
                result = self.handler.submit(dict(draft_id='draft'))
                self.assertEqual(result['phase'], 'ready')
                self.assertIsNone(self.draft.parameter)
                self.assertEqual(self.draft.config, original.config)
                self.assertEqual(self.draft.selections, original.selections)
        self.assertEqual(self.store.save_draft.call_count, 3)
        self.snake.submit_simulation.assert_not_called()

    def test_uniqueness_lookup_failure_propagates_without_saving_or_running(self):
        self.snake.is_config_unique.side_effect = RuntimeError('lookup failed')
        original = deepcopy(self.draft)
        with self.assertRaisesRegex(RuntimeError, 'lookup failed'):
            self.handler.submit(dict(draft_id='draft'))
        self.assertEqual(self.draft, original)
        self.store.save_draft.assert_not_called()
        self.snake.submit_simulation.assert_not_called()

    def test_invalid_arguments_are_rejected_before_loading_the_draft(self):
        for payload in (None, {}, dict(draft_id=1), dict(draft_id='draft', parameter='gamma')):
            self.assertEqual(self.handler.submit(payload)['status'], 'rejected')
        self.store.draft.assert_not_called()

    def test_failed_persistence_propagates_without_submission(self):
        self.store.save_draft.side_effect = RuntimeError('write failed')
        with self.assertRaisesRegex(RuntimeError, 'write failed'):
            self.handler.submit(dict(draft_id='draft'))
        self.snake.submit_simulation.assert_not_called()
