"""Exercise the shared seed request and both durable SnakeLab runs."""

from copy import deepcopy
from dataclasses import replace
import json
import unittest
from unittest.mock import Mock, patch

from jsonschema import ValidationError

from ax3l.activity.ViewConfiguration import view_values
from ax3l.app.experiment.ExperimentLoop import ExperimentLoop
from ax3l.constants.DViewConversation import DViewConversation
from ax3l.entities.ExperimentState import ExperimentState
from ax3l.entities.ExperimentView import VIEWS
from ax3l.entities.ViewProposal import ViewProposal
from ax3l.interface.SimulationConfiguration import SimulationConfiguration
from ax3l.interface.ViewConversation import ViewConversation
from test_view_experiments import blocks, tool_name
from view_cycle_fixtures import FakeSnake, LocalLLM, MemoryEvents, MemoryLog, MemoryStore, new_seed_proposal


class SeedRotationTests(unittest.TestCase):
    def setUp(self):
        self.log = MemoryLog()
        self.store = MemoryStore(self.log)
        self.snake = FakeSnake((10, 9, 4, 8))
        self.model = LocalLLM(new_seed_proposal)
        self.addCleanup(self.model.close)
        self.enterContext(patch('ax3l.app.experiment.ExperimentLoop.ExperimentDb', return_value=self.store))
        self.enterContext(patch('ax3l.app.experiment.ExperimentLoop.EventLogDb',
                               return_value=MemoryEvents(self.log)))
        self.enterContext(patch('ax3l.app.experiment.ExperimentLoop.shuffle',
                               side_effect=lambda names: names.reverse()))

    def loop(self):
        return ExperimentLoop(self.log, self.model.llm, self.snake)

    def reset(self, scores=(10, 9, 4, 8)):
        self.log.events.clear()
        self.store.state = None
        self.store.snapshots.clear()
        self.model.requests.clear()
        self.snake = FakeSnake(scores)

    def unchanged_proposal(self, request):
        response = new_seed_proposal(request)
        if tool_name(request) == 'submit_view':
            if request['messages'][0]['content'].startswith('This configuration is a duplicate,'):
                return response
            function = response['choices'][0]['message']['tool_calls'][0]['function']
            arguments = json.loads(function['arguments'])
            arguments['values'] = {name: True if name == DViewConversation.NEW_SEED else field['value']
                                   for name, field in blocks(request)[1].items()}
            function['arguments'] = json.dumps(arguments)
        return response

    def test_any_view_can_request_a_seed_and_false_does_not_lock_later_views(self):
        for requester in range(len(VIEWS)):
            with self.subTest(requester=requester):
                order = list(reversed(VIEWS))
                config = SimulationConfiguration.defaults()
                state = ExperimentState(
                    'seed-request', 'choosing', deepcopy(config), order=order,
                    previous={name: ViewProposal('Previous hypothesis.', view_values(view, config))
                              for name, view in VIEWS.items()},
                    observations={name: 'Baseline observations.' for name in VIEWS},
                )
                def respond(request):
                    response = LocalLLM.proposal(request)
                    if len(state.proposals) == requester:
                        function = response['choices'][0]['message']['tool_calls'][0]['function']
                        arguments = json.loads(function['arguments'])
                        arguments['values'][DViewConversation.NEW_SEED] = True
                        function['arguments'] = json.dumps(arguments)
                    return response
                self.model.respond = respond
                for index, name in enumerate(order):
                    self.loop()._choose_view(state)
                    parameters, readonly = blocks(self.model.requests[-1])[1:]
                    properties = self.model.requests[-1]['tools'][0]['function']['parameters']['properties']
                    self.assertEqual(set(parameters), set(properties['values']['properties']))
                    self.assertNotIn('seed', parameters)
                    self.assertEqual(readonly['seed'], config['seed'])
                    if index <= requester:
                        self.assertIs(parameters[DViewConversation.NEW_SEED]['value'], False)
                        self.assertNotIn(DViewConversation.NEW_SEED, readonly)
                    else:
                        self.assertNotIn(DViewConversation.NEW_SEED, parameters)
                        self.assertIs(readonly[DViewConversation.NEW_SEED], True)
                    state = self.store.load()
                    self.assertEqual(state.new_seed, index >= requester)
                    self.assertNotIn(DViewConversation.NEW_SEED, state.config)
                self.assertEqual(state.config['seed'], config['seed'] + 1)
                self.assertTrue(state.seed_baseline)
                self.assertEqual(state.phase, 'ready')
        self.assertEqual(self.snake.submissions, [])

    def test_both_runs_use_incremented_seed_and_compare_against_the_new_baseline(self):
        for baseline_score, candidate_score in ((4, 8), (4, 3), (4, 4), (14, 12)):
            with self.subTest(baseline=baseline_score, candidate=candidate_score):
                self.reset((10, 9, baseline_score, candidate_score))
                self.loop().run(cycles=1)
                initial, synthetic, baseline, candidate = self.snake.results
                old_config, synthetic_config, new_baseline, new_candidate = self.snake.submissions
                self.assertEqual(new_baseline, dict(old_config, seed=old_config['seed'] + 1))
                self.assertEqual(new_candidate['seed'], new_baseline['seed'])
                self.assertEqual(new_baseline['training'], old_config['training'])
                self.assertEqual(new_candidate['training']['learning_rate'], .002)
                for config in self.snake.submissions:
                    self.assertNotIn(DViewConversation.NEW_SEED, config)
                state = self.store.load()
                won = candidate_score > baseline_score
                self.assertEqual(state.golden_run_id, candidate if won else baseline)
                self.assertEqual(state.reference_run_id, baseline)
                self.assertEqual(state.latest_run_id, candidate)
                comparison = self.store.comparison(candidate)
                self.assertEqual(comparison['golden_run_id'], baseline)
                promotions = [e['process_id'] for e in self.log.events if e['name'] == 'golden_config_created']
                self.assertEqual(promotions, [initial, baseline] + ([candidate] if won else []))
                self.assertEqual(len(self.model.requests), 12)
                self.assertEqual([tool_name(r) for r in self.model.requests],
                                 ['submit_observations'] * 4 + ['submit_view'] * 4 + ['submit_observations'] * 4)
                next_cycle = self.loop()._next_cycle(state)
                self.assertFalse(next_cycle.new_seed)
                self.assertFalse(next_cycle.seed_baseline)
                self.assertEqual(next_cycle.config['seed'], new_baseline['seed'])

    def test_seed_only_request_revises_the_duplicate_candidate_after_the_baseline(self):
        self.model.respond = self.unchanged_proposal
        self.loop().run(cycles=1)
        self.assertEqual(len(self.snake.submissions), 4)
        self.assertNotEqual(self.snake.submissions[2], self.snake.submissions[3])
        self.assertEqual(self.snake.submissions[2]['seed'], self.snake.submissions[3]['seed'])
        self.assertNotEqual(self.snake.submissions[0]['seed'], self.snake.submissions[2]['seed'])
        self.assertTrue(self.model.requests[8]['messages'][0]['content'].startswith(
            'This configuration is a duplicate, please select different values.'))

    def test_omitting_the_request_keeps_a_single_candidate_run_on_the_current_seed(self):
        def omit(request):
            response = LocalLLM.proposal(request)
            if tool_name(request) == 'submit_view':
                function = response['choices'][0]['message']['tool_calls'][0]['function']
                arguments = json.loads(function['arguments'])
                arguments['values'].pop(DViewConversation.NEW_SEED)
                function['arguments'] = json.dumps(arguments)
            return response
        self.model.respond = omit
        self.loop().run(cycles=1)
        self.assertEqual(len(self.snake.submissions), 3)
        self.assertEqual([config['seed'] for config in self.snake.submissions], [1970, 1970, 1970])

    def test_consecutive_cycles_increment_once_each_and_reset_the_request(self):
        self.snake = FakeSnake((10, 9, 4, 8, 3, 6))
        self.loop().run(cycles=2)
        self.assertEqual([config['seed'] for config in self.snake.submissions], [1970, 1970, 1971, 1971, 1972, 1972])
        for request in (self.model.requests[4], self.model.requests[12]):
            self.assertIs(blocks(request)[1][DViewConversation.NEW_SEED]['value'], False)

    def test_restart_resumes_each_run_and_does_not_repeat_committed_promotions(self):
        boundaries = ('baseline-running', 'baseline-promoted', 'candidate-running', 'candidate-promoted')
        for boundary in boundaries:
            with self.subTest(boundary=boundary):
                self.reset()
                save = self.store.save
                def interrupt(state):
                    if boundary == 'baseline-promoted' and state.new_seed and not state.seed_baseline \
                            and state.phase == 'ready':
                        raise KeyboardInterrupt()
                    if boundary == 'candidate-promoted' and state.new_seed and state.phase == 'evaluating':
                        raise KeyboardInterrupt()
                    save(state)
                    if state.phase == 'running' and state.new_seed:
                        if (boundary == 'baseline-running' and state.seed_baseline) or \
                                (boundary == 'candidate-running' and not state.seed_baseline):
                            raise KeyboardInterrupt()
                with patch.object(self.store, 'save', side_effect=interrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        self.loop().run(cycles=1)
                self.loop().run(cycles=1)
                self.assertEqual(len(self.snake.submissions), 4)
                self.assertEqual(len(self.model.requests), 12)
                names = [e['name'] for e in self.log.events]
                self.assertEqual(names.count('golden_config_created'), 3)
                self.assertEqual(names.count('simulation_submitted'), 4)
                self.assertEqual(names.count('simulation_completed'), 4)
                self.assertEqual(names.count('configuration_compared'), 2)

    def test_lost_replies_reconcile_both_runs_including_a_revised_duplicate(self):
        for submission, unchanged in ((3, False), (4, False), (4, True)):
            with self.subTest(submission=submission, unchanged=unchanged):
                self.reset()
                self.model.respond = self.unchanged_proposal if unchanged else new_seed_proposal
                submit = self.snake.submit_simulation
                def lost_reply(config):
                    run_id = submit(config)
                    if len(self.snake.submissions) == submission:
                        raise TimeoutError('Lost acknowledgement')
                    return run_id
                with patch.object(self.snake, 'submit_simulation', side_effect=lost_reply):
                    with self.assertRaises(TimeoutError):
                        self.loop().run(cycles=1)
                self.assertEqual(self.store.load().phase, 'submitting')
                self.assertEqual(self.store.load().seed_baseline, submission == 3)
                self.loop().run(cycles=1)
                self.assertEqual(len(self.snake.submissions), 4)
                self.assertEqual(self.store.load().phase, 'completed')
                self.assertEqual(len(self.model.requests), 13 if unchanged else 12)

    def test_failed_seed_baseline_blocks_candidate_until_resolved(self):
        for status in ('failed', 'cancelled'):
            with self.subTest(status=status):
                self.reset()
                submit = self.snake.submit_simulation
                def terminal(config):
                    run_id = submit(config)
                    if len(self.snake.submissions) == 3:
                        self.snake.results[run_id]['status'] = status
                    return run_id
                with patch.object(self.snake, 'submit_simulation', side_effect=terminal):
                    with self.assertRaisesRegex(RuntimeError, status):
                        self.loop().run(cycles=1)
                state = self.store.load()
                self.assertTrue(state.seed_baseline)
                self.assertEqual(len(self.snake.submissions), 3)
                self.assertEqual(len(self.model.requests), 8)
                self.snake.results[state.run_id]['status'] = 'completed'
                self.loop().run(cycles=1)
                self.assertEqual(len(self.snake.submissions), 4)

    def test_an_existing_seed_baseline_does_not_replace_an_unacknowledged_revised_candidate(self):
        self.model.respond = self.unchanged_proposal
        submit = self.snake.submit_simulation
        def no_reply(config):
            if len(self.snake.submissions) == 3:
                raise TimeoutError('No candidate acknowledgement')
            return submit(config)
        with patch.object(self.snake, 'submit_simulation', side_effect=no_reply):
            with self.assertRaises(TimeoutError):
                self.loop().run(cycles=1)
        state = self.store.load()
        self.assertFalse(state.seed_baseline)
        self.assertIsNone(state.preceding_match)
        with self.assertRaisesRegex(RuntimeError, 'will not be retried'):
            self.loop().run(cycles=1)
        self.assertEqual(len(self.snake.submissions), 3)

    def test_seed_limits_are_left_to_snakelab(self):
        config = SimulationConfiguration.defaults()
        config['seed'] = SimulationConfiguration.field(('seed',))['maximum']
        run_id = self.snake.submit_simulation(config)
        self.log.log('golden_config_created', 'Configuration', 'INFO', 'Existing golden.', process_id=run_id)
        self.loop().run(cycles=1)
        self.assertEqual(len(self.snake.submissions), 3)
        self.assertEqual(self.snake.submissions[1]['seed'], config['seed'] + 1)
        self.assertEqual(self.snake.submissions[2]['seed'], config['seed'] + 1)


class SeedRequestBoundaryTests(unittest.TestCase):
    def proposal(self, view, values):
        llm, log = Mock(url='http://local'), MemoryLog()
        arguments = dict(hypothesis='Try a new seed.', values=values)
        llm.complete.return_value = 200, '', json.dumps(dict(choices=[dict(message=dict(tool_calls=[
            dict(function=dict(name='submit_view', arguments=json.dumps(arguments)))
        ]))])).encode()
        return ViewConversation(llm, log).propose(view, 'Tune.', 'test')

    def test_a_view_can_submit_just_the_seed_request(self):
        for view in VIEWS.values():
            with self.subTest(view=view.name):
                self.assertEqual(self.proposal(view, {'new seed': True}).values, {'new seed': True})

    def test_a_later_view_cannot_resubmit_or_reverse_the_locked_request(self):
        for view in VIEWS.values():
            locked = replace(view, parameters=tuple(name for name in view.parameters
                                                   if name != DViewConversation.NEW_SEED))
            for value in (True, False):
                with self.subTest(view=view.name, value=value):
                    with self.assertRaises(ValidationError):
                        self.proposal(locked, {'new seed': value})

    def test_only_a_boolean_request_is_accepted_and_numeric_seed_edits_are_rejected(self):
        for view in VIEWS.values():
            for values in ({'seed': 1971}, {'new seed': 1}, {'new seed': 'true'}, {'new seed': None}):
                with self.subTest(view=view.name, values=values):
                    with self.assertRaises(ValidationError):
                        self.proposal(view, values)


if __name__ == '__main__':
    unittest.main()
