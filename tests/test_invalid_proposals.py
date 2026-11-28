"""Invalid proposals never reach SnakeLab, including checkpoints from older versions."""

from copy import deepcopy
import json
from unittest.mock import Mock, patch

from ax3l.activity.ViewConfiguration import apply_values
from ax3l.entities.ExperimentState import ExperimentState
from ax3l.entities.ExperimentView import VIEWS
from ax3l.entities.ViewProposal import ViewProposal
from ax3l.interface.SimulationConfiguration import SimulationConfiguration
from experiment_fixture import ExperimentFixture
from test_view_experiments import prompt_text
from view_cycle_fixtures import FakeSnake, LocalLLM


class InvalidProposalTests(ExperimentFixture):
    def saved_proposal(self, phase, *, invalid=True):
        config = SimulationConfiguration.defaults()
        config['training']['gamma'] = .99
        golden = self.snake.submit_simulation(config)
        self.log.log('golden_config_created', 'Configuration', 'INFO', 'Baseline.', process_id=golden)
        values = {'training.gamma': .9999999999999999 if invalid else .95}
        state = ExperimentState('saved-training', phase, apply_values(config, values),
                                golden_run_id=golden, reference_run_id=golden, latest_run_id=golden,
                                order=list(VIEWS), view_index=list(VIEWS).index('training'), failures=3,
                                proposals={'training': ViewProposal('Rejected hypothesis.', values)})
        self.store.save(state)
        return state

    def test_invalid_values_are_corrected_before_any_submission_or_checkpoint_accepts_them(self):
        self.shuffle.side_effect = lambda names: names.sort(key=lambda name: name != 'training')
        respond = self.model.respond
        def invalid_first(request):
            response = respond(request)
            if len(self.model.requests) == 1:
                function = response['choices'][0]['message']['tool_calls'][0]['function']
                arguments = json.loads(function['arguments'])
                arguments['values']['training.gamma'] = .9999999999999999
                function['arguments'] = json.dumps(arguments)
            if len(self.model.requests) == 2:
                self.assertEqual(len(self.snake.submissions), 1)
                self.assertEqual(self.store.load().phase, 'choosing')
            return response
        self.model.respond = invalid_first
        self.loop().run(cycles=1)
        self.assertEqual(len(self.snake.submissions), 2)
        self.assertTrue(all(config['training']['gamma'] <= .99 for config in self.snake.submissions))
        self.assertTrue(all(state.config['training']['gamma'] <= .99 for state in self.store.snapshots))
        self.assertEqual([len(request['messages']) for request in self.model.requests], [1, 3, 1])
        self.assertEqual(self.event_count('tool_execution_failed'), 1)
        self.assertEqual(self.event_count('conversation_started'), 2)

    def test_saved_invalid_proposals_return_to_the_same_view(self):
        for phase in ('ready', 'submitting', 'revising'):
            with self.subTest(phase=phase):
                self.store.state = None
                self.model.requests.clear()
                self.log.events.clear()
                self.snake = FakeSnake((10, 9))
                original = self.saved_proposal(phase)
                self.loop().run(cycles=1)
                text = prompt_text(self.model.requests[0])
                self.assertTrue(text.startswith('The parameters supplied'))
                self.assertIn('## Rejected proposal', text)
                self.assertIn('Rejected hypothesis.', text)
                self.assertIn('0.9999999999999999', text)
                state = self.store.load()
                self.assertEqual(state.experiment_id, original.experiment_id)
                self.assertEqual(state.view_name, 'training')
                self.assertEqual(state.golden_run_id, original.golden_run_id)
                self.assertEqual(state.failures, 4)
                self.assertEqual(len(self.snake.submissions), 2)
                self.assertTrue(all(config['training']['gamma'] <= .99 for config in self.snake.submissions))
                self.shuffle.assert_not_called()

    def test_replacement_does_not_keep_an_invalid_value_omitted_by_the_llm(self):
        original = self.saved_proposal('submitting')
        respond = self.model.respond
        def omit_gamma(request):
            response = respond(request)
            if request['tools'][0]['function']['name'] == 'submit_view':
                function = response['choices'][0]['message']['tool_calls'][0]['function']
                function['arguments'] = json.dumps(dict(hypothesis='Keep golden gamma.',
                                                       values={'training.batch_size': 32}))
            return response
        self.model.respond = omit_gamma
        self.loop().run(cycles=1)
        self.assertEqual(self.snake.submissions[-1]['training']['gamma'], .99)
        self.assertEqual(self.snake.submissions[-1]['training']['batch_size'], 32)
        self.assertEqual(self.store.load().proposals['training'].values, {'training.batch_size': 32})
        self.assertEqual(self.store.load().golden_run_id, original.golden_run_id)

    def test_restart_during_correction_keeps_the_rejection_and_does_not_resubmit(self):
        self.saved_proposal('submitting')
        self.model.respond = Mock(side_effect=KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            self.loop().run(cycles=1)
        self.assertEqual(self.store.load().phase, 'correcting')
        self.assertEqual(len(self.snake.submissions), 1)
        first = deepcopy(self.model.requests[0])
        self.model.respond = LocalLLM.proposal
        self.loop().run(cycles=1)
        self.assertEqual(first['messages'], self.model.requests[1]['messages'])
        self.assertEqual(len(self.snake.submissions), 2)

    def test_existing_submitted_run_takes_precedence_over_the_new_validation_rules(self):
        original = self.saved_proposal('submitting')
        submitted = self.snake.submit_simulation(original.config)
        self.loop().run(cycles=1)
        self.assertEqual(self.store.load().run_id, submitted)
        self.assertEqual(len(self.snake.submissions), 2)
        self.assertEqual(len(self.model.requests), 1)
        self.assertEqual(self.model.requests[0]['tools'][0]['function']['name'], 'submit_observations')

    def test_valid_unresolved_submissions_are_not_retried(self):
        self.saved_proposal('submitting', invalid=False)
        with patch.object(self.snake, 'submit_simulation') as submit:
            with self.assertRaisesRegex(RuntimeError, 'will not be retried'):
                self.loop().run(cycles=1)
        submit.assert_not_called()
        self.assertEqual(self.store.load().phase, 'submitting')
        self.assertEqual(self.model.requests, [])
