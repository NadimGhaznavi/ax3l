"""Seed requests stage one durable unique change without accepting numeric values."""

from copy import deepcopy
from dataclasses import asdict
import json
import unittest
from unittest.mock import Mock, patch

from ax3l.app.snakelab.RequestSeedChangeHandler import RequestSeedChangeHandler
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
from ax3l.interface.SimulationConfiguration import SimulationConfiguration
from ax3l.server.ToolHandler import handle_tool
from ax3l.zmq.ZMQMsg import ZMQMsg


class RequestSeedChangeHandlerTests(unittest.TestCase):
    def setUp(self):
        shared = 'ax3l.app.snakelab.SubmitSingleValueHandler.'
        self.snake = self.enterContext(patch(shared + 'SnakeLab')).return_value
        self.snake.is_config_unique.return_value = True
        self.baseline = SimulationConfiguration.defaults()
        self.snake.get_run_result.return_value = dict(config=self.baseline)
        self.experiments = self.enterContext(patch(
            'ax3l.app.snakelab.RequestSeedChangeHandler.ExperimentDb')).return_value
        self.draft = ConfigurationDraft('draft', 'gold', {'golden': 'gold'},
                                        SimulationConfiguration.defaults(), ['layers'], 'choosing',
                                        parameter='seed', decision_expires_at=1000)
        self.draft.config['model']['layers'] = 2
        self.experiments.draft.return_value = self.draft
        self.db = Mock()
        self.handler = RequestSeedChangeHandler(self.db)

    def test_request_increments_seed_and_preserves_every_other_setting_without_running(self):
        original = deepcopy(self.draft)
        result = self.handler.submit({'draft_id': 'draft'})
        self.assertEqual(result, dict(status='ok', draft_id='draft', phase='reviewing', seed=1971))
        self.assertEqual(self.draft.config, {**original.config, 'seed': 1971})
        self.assertEqual(self.draft.selections, ['layers', 'seed'])
        self.assertEqual(self.draft.references, original.references)
        self.assertEqual(self.draft.decision_expires_at, original.decision_expires_at)
        self.assertIsNone(self.draft.parameter)
        self.experiments.save_draft.assert_called_once_with(self.draft)
        self.snake.submit_simulation.assert_not_called()
        self.db.log.assert_not_called()

    def test_tested_seeds_are_skipped_without_changing_the_saved_draft(self):
        original = deepcopy(self.draft)
        checked = []

        def unique(candidate):
            self.assertEqual(self.draft, original)
            checked.append(deepcopy(candidate))
            return candidate['seed'] == 1973

        self.snake.is_config_unique.side_effect = unique
        result = self.handler.submit({'draft_id': 'draft'})
        self.assertEqual([config['seed'] for config in checked], [1971, 1972, 1973, 1973])
        self.assertTrue(all(config == {**original.config, 'seed': config['seed']} for config in checked[:-1]))
        self.assertEqual(checked[-1], {**self.baseline, 'seed': 1973})
        self.assertEqual(result['seed'], 1973)
        self.experiments.save_draft.assert_called_once()

    def test_stored_golden_baselines_are_skipped_even_when_the_draft_is_unique(self):
        self.snake.is_config_unique.side_effect = lambda config: config != {**self.baseline, 'seed': 1971}
        result = self.handler.submit({'draft_id': 'draft'})
        self.assertEqual(result['seed'], 1972)
        self.assertEqual(self.draft.config['model']['layers'], 2)

    def test_seed_only_request_checks_each_complete_configuration_once(self):
        self.draft.config = deepcopy(self.baseline)
        self.draft.selections = []
        self.snake.is_config_unique.side_effect = [False, True]
        self.assertEqual(self.handler.submit({'draft_id': 'draft'})['seed'], 1972)
        self.assertEqual(self.snake.is_config_unique.call_count, 2)

    def test_values_extra_fields_and_invalid_identifiers_are_rejected_before_reading(self):
        for payload in (None, {}, {'draft_id': None}, {'draft_id': ''},
                        {'draft_id': 'draft', 'seed': 100}, {'draft_id': 'draft', 'value': 100},
                        {'draft_id': 'draft', 'parameter': 'seed'}):
            with self.subTest(payload=payload):
                self.assertEqual(self.handler.submit(payload)['status'], 'rejected')
        self.experiments.draft.assert_not_called()
        self.experiments.save_draft.assert_not_called()
        self.snake.is_config_unique.assert_not_called()

    def test_wrong_draft_phase_or_parameter_cannot_increment_the_seed(self):
        original = deepcopy(self.draft)
        self.assertEqual(self.handler.submit({'draft_id': 'stale'})['status'], 'rejected')
        self.assertEqual(self.draft, original)
        for phase in ('selecting_parameter', 'reviewing', 'ready', 'submitting', 'submitted', 'completed'):
            self.draft.phase = phase
            self.assertEqual(self.handler.submit({'draft_id': 'draft'})['status'], 'rejected')
        self.draft.phase, self.draft.parameter = 'choosing', 'layers'
        self.assertEqual(self.handler.submit({'draft_id': 'draft'})['status'], 'rejected')
        self.experiments.draft.return_value = None
        self.assertEqual(self.handler.submit({'draft_id': 'draft'})['status'], 'rejected')
        self.snake.is_config_unique.assert_not_called()
        self.experiments.save_draft.assert_not_called()

    def test_repeating_an_accepted_request_after_restart_reports_exhaustion_without_incrementing(self):
        self.handler.submit({'draft_id': 'draft'})
        self.draft = ConfigurationDraft(**json.loads(json.dumps(asdict(self.draft))))
        self.experiments.draft.return_value = self.draft
        saved = deepcopy(self.draft)
        self.snake.reset_mock()
        result = self.handler.submit({'draft_id': 'draft'})
        self.assertEqual(result['status'], 'rejected')
        self.assertEqual(result['code'], 'parameter_space_exhausted')
        self.assertIn('seed has already been changed', result['reason'])
        self.assertEqual(self.draft, saved)
        self.experiments.save_draft.assert_called_once()
        self.snake.get_run_result.assert_not_called()
        self.snake.is_config_unique.assert_not_called()
        self.snake.submit_simulation.assert_not_called()

    def test_seed_limit_rejects_without_wrapping_or_saving(self):
        self.draft.config['seed'] = SimulationConfiguration.field(('seed',))['maximum']
        original = deepcopy(self.draft)
        result = self.handler.submit({'draft_id': 'draft'})
        self.assertEqual(result['status'], 'rejected')
        self.assertIn('Cannot increment the seed', result['reason'])
        self.assertEqual(self.draft, original)
        self.experiments.save_draft.assert_not_called()
        self.snake.is_config_unique.assert_not_called()

    def test_uniqueness_failure_leaves_the_draft_unmodified_and_propagates(self):
        original = deepcopy(self.draft)
        self.snake.is_config_unique.side_effect = RuntimeError('database unavailable')
        with self.assertRaisesRegex(RuntimeError, 'database unavailable'):
            self.handler.submit({'draft_id': 'draft'})
        self.assertEqual(self.draft, original)
        self.experiments.save_draft.assert_not_called()

    def test_persistence_failure_propagates_without_submitting_a_simulation(self):
        self.experiments.save_draft.side_effect = RuntimeError('write failed')
        with self.assertRaisesRegex(RuntimeError, 'write failed'):
            self.handler.submit({'draft_id': 'draft'})
        self.experiments.save_draft.assert_called_once()
        self.snake.submit_simulation.assert_not_called()

    def test_dispatch_uses_the_seed_handler_and_closes_its_database(self):
        with patch('ax3l.server.ToolHandler.DbMgr', return_value=self.db):
            result = handle_tool(ZMQMsg(sender='test', target='snakelab', method='request_seed_change',
                                        payload={'draft_id': 'draft'}))
        self.assertEqual(result['seed'], 1971)
        self.db.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
