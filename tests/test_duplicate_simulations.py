"""Revise duplicate drafts through a randomly chosen, resumable Selection view."""

from copy import deepcopy
import json
import unittest
from unittest.mock import Mock, patch

from ax3l.activity.ViewConfiguration import view_values
from ax3l.app.experiment.ExperimentLoop import ExperimentLoop
from ax3l.entities.ExperimentState import ExperimentState
from ax3l.entities.ExperimentView import VIEWS
from ax3l.entities.ViewProposal import ViewProposal
from ax3l.interface.SimulationConfiguration import SimulationConfiguration
from test_view_experiments import blocks, prompt_text, tool_name
from view_cycle_fixtures import FakeSnake, LocalLLM, MemoryEvents, MemoryLog, MemoryStore


NOTICE = 'This configuration is a duplicate, please select different values.'


class DuplicateSimulationTests(unittest.TestCase):
    def setUp(self):
        self.log = MemoryLog()
        self.store = MemoryStore(self.log)
        self.snake = FakeSnake((10, 12, 9, 8))
        self.requests = []
        self.respond = LocalLLM.proposal
        self.llm = Mock(url='http://local')
        self.llm.complete.side_effect = self.complete
        self.enterContext(patch('ax3l.app.experiment.ExperimentLoop.ExperimentDb', return_value=self.store))
        self.enterContext(patch('ax3l.app.experiment.ExperimentLoop.EventLogDb',
                               return_value=MemoryEvents(self.log)))
        self.choose = self.enterContext(patch('ax3l.app.experiment.ExperimentLoop.choice', return_value='architecture'))

    def complete(self, payload):
        request = json.loads(payload)
        self.requests.append(request)
        return 200, '', json.dumps(self.respond(request)).encode()

    def loop(self):
        return ExperimentLoop(self.log, self.llm, self.snake)

    def ready(self, seed=1970):
        config = SimulationConfiguration.defaults()
        config['seed'] = seed
        run_id = self.snake.submit_simulation(config)
        self.log.log('golden_config_created', 'Configuration', 'INFO', 'Existing golden.', process_id=run_id)
        proposals = {name: ViewProposal(f'Current {name} hypothesis.', view_values(view, config))
                     for name, view in VIEWS.items()}
        state = ExperimentState('duplicate-cycle', 'ready', deepcopy(config), golden_run_id=run_id,
                                reference_run_id=run_id, latest_run_id=run_id, order=list(reversed(VIEWS)),
                                proposals=proposals, observations={name: 'Previous observations.' for name in VIEWS})
        self.store.save(state)
        return state

    def test_any_of_the_four_views_can_revise_a_duplicate_without_changing_other_choices(self):
        for name in VIEWS:
            with self.subTest(view=name):
                self.log.events.clear()
                self.requests.clear()
                self.snake = FakeSnake((10, 12))
                self.choose.reset_mock()
                self.choose.return_value = name
                original = self.ready()
                self.loop().run(cycles=1)
                self.choose.assert_called_once_with(list(VIEWS))
                request = self.requests[0]
                self.assertEqual(tool_name(request), 'submit_view')
                self.assertTrue(prompt_text(request).startswith(NOTICE + '\n\n## Task:'))
                previous, parameters, readonly = blocks(request)
                self.assertEqual(previous, original.proposals[name].values)
                self.assertEqual(readonly['seed'], original.config['seed'])
                self.assertTrue(set(parameters) <= set(VIEWS[name].parameters))
                self.assertNotIn('training.gamma', parameters)
                self.assertNotIn('training.sequence_length', parameters)
                state = self.store.load()
                self.assertEqual(len(self.snake.submissions), 2)
                self.assertNotEqual(self.snake.submissions[0], self.snake.submissions[1])
                self.assertEqual(state.phase, 'completed')
                self.assertIsNone(state.revision_view)
                self.assertEqual(state.order, original.order)
                for other in VIEWS:
                    if other != name:
                        self.assertEqual(state.proposals[other], original.proposals[other])
                for path, value in original.proposals[name].values.items():
                    self.assertIn(path, state.proposals[name].values)
                    if path not in parameters:
                        self.assertEqual(state.proposals[name].values[path], value)
                self.assertEqual(len(self.requests), 5)

    def test_a_second_duplicate_selects_again_before_any_simulation_is_submitted(self):
        self.ready()
        self.choose.side_effect = ['architecture', 'exploration']
        def unchanged_once(request):
            self.assertEqual(len(self.snake.submissions), 1)
            response = LocalLLM.proposal(request)
            if len(self.requests) == 1:
                function = response['choices'][0]['message']['tool_calls'][0]['function']
                arguments = json.loads(function['arguments'])
                parameters = blocks(request)[1]
                arguments['values'] = {name: field['value'] for name, field in parameters.items()}
                function['arguments'] = json.dumps(arguments)
                return response
            self.respond = LocalLLM.proposal
            return response
        self.respond = unchanged_once
        self.loop().run(cycles=1)
        self.assertEqual(self.choose.call_count, 2)
        self.assertEqual(len(self.snake.submissions), 2)
        self.assertIn('Architecture Tuning', prompt_text(self.requests[0]))
        self.assertIn('Exploration Tuning', prompt_text(self.requests[1]))
        self.assertTrue(all(prompt_text(request).startswith(NOTICE) for request in self.requests[:2]))

    def test_restart_keeps_the_saved_random_view_and_duplicate_notice(self):
        self.ready()
        def interrupt():
            if self.store.load().phase == 'revising':
                raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.loop().run(cycles=1, check=interrupt)
        self.assertEqual(self.store.load().revision_view, 'architecture')
        self.assertEqual(self.requests, [])
        self.assertEqual(len(self.snake.submissions), 1)
        self.loop().run(cycles=1)
        self.choose.assert_called_once()
        self.assertTrue(prompt_text(self.requests[0]).startswith(NOTICE))
        self.assertIn('Architecture Tuning', prompt_text(self.requests[0]))
        self.assertEqual(len(self.snake.submissions), 2)

    def test_revising_an_incremented_seed_does_not_increment_it_again(self):
        state = self.ready(seed=1971)
        state.new_seed = True
        state.proposals['reward-signals'].values['new seed'] = True
        self.store.save(state)
        self.loop().run(cycles=1)
        self.assertEqual([config['seed'] for config in self.snake.submissions], [1971, 1971])
        parameters, readonly = blocks(self.requests[0])[1:]
        self.assertNotIn('new seed', parameters)
        self.assertTrue(readonly['new seed'])

    def test_a_distinct_seed_is_not_a_duplicate(self):
        state = self.ready()
        state.config['seed'] += 1
        self.store.save(state)
        self.loop().run(cycles=1)
        self.choose.assert_not_called()
        self.assertTrue(all(tool_name(request) == 'submit_observations' for request in self.requests))
        self.assertEqual([config['seed'] for config in self.snake.submissions], [1970, 1971])

    def test_a_revision_can_request_a_new_seed_and_then_revise_the_matching_candidate(self):
        self.ready()
        self.choose.side_effect = ['reward-signals', 'architecture']
        def request_seed(request):
            response = LocalLLM.proposal(request)
            function = response['choices'][0]['message']['tool_calls'][0]['function']
            function['arguments'] = json.dumps(dict(hypothesis='Test a new seed.', values={'new seed': True}))
            self.respond = LocalLLM.proposal
            return response
        self.respond = request_seed
        self.loop().run(cycles=1)
        self.assertEqual(self.choose.call_count, 2)
        self.assertEqual([config['seed'] for config in self.snake.submissions], [1970, 1971, 1971])
        self.assertNotEqual(self.snake.submissions[1], self.snake.submissions[2])
        self.assertTrue(all(prompt_text(request).startswith(NOTICE) for request in self.requests[:2]))

    def test_a_synthetic_duplicate_uses_its_startup_choices_without_previous_observations(self):
        state = self.ready()
        state.synthetic = True
        state.order = []
        state.observations = {}
        self.store.save(state)
        def interrupt():
            if len(self.snake.submissions) == 2:
                raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.loop().run(cycles=1, check=interrupt)
        self.assertEqual(len(self.requests), 1)
        self.assertTrue(prompt_text(self.requests[0]).startswith(NOTICE))
        self.assertEqual(blocks(self.requests[0])[0], state.proposals['architecture'].values)
        self.assertNotEqual(self.snake.submissions[0], self.snake.submissions[1])
