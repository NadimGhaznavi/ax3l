"""Exercise the view cycle through real prompt rendering and local HTTP inference."""

from copy import deepcopy
import json
import re
import unittest
from unittest.mock import Mock, patch

from jsonschema import ValidationError

from ax3l.activity.ViewConfiguration import apply_values, other_parameters
from ax3l.app.snakelab.ExperimentLoop import ExperimentLoop
from ax3l.entities.ExperimentView import VIEWS
from ax3l.interface.SimulationConfiguration import SCHEMA, SimulationConfiguration
from ax3l.interface.ViewConversation import ViewConversation
from view_cycle_fixtures import FakeSnake, LocalLLM, MemoryEvents, MemoryLog, MemoryStore


def blocks(request):
    content = request['messages'][0]['content']
    return [json.loads(block) for block in re.findall(r'```json\n(.*?)\n```', content, re.S)]


class ViewConfigurationTests(unittest.TestCase):
    def test_four_views_partition_every_tunable_field(self):
        def fields(schema, path=''):
            for key, value in schema['properties'].items():
                name = f'{path}.{key}' if path else key
                if value['type'] == 'object':
                    yield from fields(value, name)
                elif 'const' not in value:
                    yield name
        editable = [name for view in VIEWS.values() for name in view.parameters]
        self.assertEqual(len(editable), len(set(editable)))
        self.assertEqual(set(editable), set(fields(SCHEMA)))

    def test_read_only_context_removes_owned_values_and_marks_only_proposals(self):
        config = SimulationConfiguration.defaults()
        original = deepcopy(config)
        view = VIEWS['training']
        other = other_parameters(view, config, {'model.layers'})
        self.assertNotIn('seed', other)
        self.assertNotIn('batch_size', other['training'])
        self.assertEqual(other['model']['layers'], '1 (draft)')
        self.assertEqual(other['model']['hidden_size'], 64)
        self.assertEqual(other['training']['sequence_length'], 4)
        changed = apply_values(config, {'model.layers': 2})
        self.assertEqual(changed['model']['layers'], 2)
        self.assertEqual(config, original)


class ViewCycleTests(unittest.TestCase):
    def setUp(self):
        self.log = MemoryLog()
        self.store = MemoryStore(self.log)
        self.snake = FakeSnake()
        self.model = LocalLLM()
        self.addCleanup(self.model.close)
        self.enterContext(patch('ax3l.app.snakelab.ExperimentLoop.ExperimentDb', return_value=self.store))
        self.enterContext(patch('ax3l.app.snakelab.ExperimentLoop.EventLogDb',
                               return_value=MemoryEvents(self.log)))
        self.shuffle = self.enterContext(patch('ax3l.app.snakelab.ExperimentLoop.shuffle',
                                               side_effect=lambda names: names.reverse()))

    def loop(self):
        return ExperimentLoop(self.log, self.model.llm, self.snake)

    def test_complete_cycles_submit_once_after_four_views_and_keep_winning_reference(self):
        self.loop().run(cycles=2)
        self.assertEqual(len(self.model.requests), 8)
        self.assertEqual(len(self.snake.submissions), 3)  # Baseline plus two complete experiments.
        self.assertEqual(self.shuffle.call_count, 2)
        state = self.store.load()
        self.assertEqual(state.order, list(reversed(VIEWS)))
        self.assertEqual(state.phase, 'completed')
        winner = list(self.snake.results)[1]
        self.assertEqual(state.golden_run_id, winner)  # Second experiment loses.
        first_trial = self.snake.submissions[1]
        for path, expected in {'game.rewards.food': 12, 'model.hidden_size': 72,
                               'training.learning_rate': .002, 'epsilon.initial': .9}.items():
            self.assertEqual(SimulationConfiguration.value_at(first_trial, tuple(path.split('.'))), expected)
        self.assertEqual(blocks(self.model.requests[4])[1]['high_score_change'], 2)
        self.assertIn('Hypothesis for exploration.', self.model.requests[4]['messages'][0]['content'])
        self.assertIn('Expected effect: A higher high score.', self.model.requests[4]['messages'][0]['content'])
        for index, request in enumerate(self.model.requests[:4]):
            previous_values, comparison, parameters, readonly = blocks(request)
            self.assertEqual(comparison['high_score_change'], 0)
            self.assertEqual(len(parameters), len(VIEWS[state.order[index]].parameters))
            if index == 0:
                self.assertNotIn('(draft)', json.dumps(readonly))
            else:
                self.assertIn('(draft)', json.dumps(readonly))
            content = request['messages'][0]['content']
            for internal in ('round-robin', 'randomized', 'seeded', 'synthetic', 'four views'):
                self.assertNotIn(internal, content.lower())
        names = [event['name'] for event in self.log.events]
        self.assertEqual(names.count('proposal_accepted'), 2)
        self.assertEqual(names.count('configuration_compared'), 2)
        self.assertEqual(names.count('golden_config_created'), 2)
        self.assertEqual(names.count('simulation_completed'), 3)
        self.assertLess(names.index('simulation_completed'), names.index('golden_config_created'))

    def test_restart_keeps_order_and_accepted_views(self):
        normal = self.store.save
        def stop_after_two(state):
            normal(state)
            if state.phase == 'choosing' and len(state.proposals) == 2:
                raise KeyboardInterrupt()
        with patch.object(self.store, 'save', side_effect=stop_after_two):
            with self.assertRaises(KeyboardInterrupt):
                self.loop().run(cycles=1)
        self.assertEqual(len(self.model.requests), 2)
        self.loop().run(cycles=1)
        self.assertEqual(len(self.model.requests), 4)
        self.assertEqual(len(self.snake.submissions), 2)
        self.shuffle.assert_called_once()

    def test_lost_submission_reply_reconciles_new_run_without_resubmitting(self):
        submit = self.snake.submit_simulation
        def lost_reply(config):
            submit(config)
            raise TimeoutError('Lost acknowledgement')
        with patch.object(self.snake, 'submit_simulation', side_effect=lost_reply):
            with self.assertRaises(TimeoutError):
                self.loop().run(cycles=1)
        self.assertEqual(self.store.load().phase, 'submitting')
        self.loop().run(cycles=1)
        self.assertEqual(len(self.snake.submissions), 2)
        self.assertEqual(len(self.model.requests), 4)

    def test_unresolved_submission_is_never_sent_again(self):
        with patch.object(self.snake, 'submit_simulation', side_effect=TimeoutError('No reply')) as submit:
            with self.assertRaises(TimeoutError):
                self.loop().run(cycles=1)
            with self.assertRaisesRegex(RuntimeError, 'will not be retried'):
                self.loop().run(cycles=1)
            submit.assert_called_once()
        self.assertEqual(self.model.requests, [])

    def test_existing_identical_run_does_not_resolve_a_new_submission(self):
        self.loop().run(cycles=1)
        winner = self.store.load().golden_run_id
        with patch.object(self.snake, 'submit_simulation', side_effect=TimeoutError('No reply')) as submit:
            with self.assertRaises(TimeoutError):
                self.loop().run(cycles=1)
            self.assertEqual(self.store.load().preceding_match, winner)
            with self.assertRaisesRegex(RuntimeError, 'will not be retried'):
                self.loop().run(cycles=1)
            submit.assert_called_once()
        self.assertEqual(len(self.snake.submissions), 2)

    def test_invalid_proposal_stops_before_candidate_submission_and_can_resume(self):
        original = self.model.respond
        def invalid(request):
            response = original(request)
            response['choices'][0]['message']['tool_calls'][0]['function']['arguments'] = json.dumps(dict(
                evaluation='Observed.', hypothesis='An invalid edit.', expected_effect='A better score.',
                values={'model.heads': 8}))
            return response
        self.model.respond = invalid
        with self.assertRaises(ValidationError):
            self.loop().run(cycles=1)
        self.assertEqual(len(self.snake.submissions), 1)
        self.assertEqual(self.store.load().proposals, {})
        self.model.respond = original
        self.loop().run(cycles=1)
        self.assertEqual(len(self.snake.submissions), 2)
        self.assertEqual(len(self.model.requests), 5)
        self.assertEqual(self.store.load().phase, 'completed')


class ProposalBoundaryTests(unittest.TestCase):
    def test_invalid_tool_results_are_rejected_once_and_conversations_always_end(self):
        view = VIEWS['reward-signals']
        template = dict(evaluation='Observed.', hypothesis='Test rewards.', expected_effect='More food.',
                        values={'game.rewards.food': 12})
        cases = [
            dict(template, values={'game.rewards.food': True}),
            dict(template, values={'game.rewards.food': 21}),
            dict(template, values={'game.rewards.food': float('nan')}),
            dict(template, values={'training.gamma': .95}),
            dict(template, values={'game.rewards.closer_to_food': 5, 'game.rewards.further_from_food': -1}),
            dict(template, hypothesis='  '),
            dict(template, values={}),
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                llm = Mock(url='http://local')
                llm.complete.return_value = (200, '', json.dumps(dict(choices=[dict(message=dict(tool_calls=[
                    dict(function=dict(name='submit_view', arguments=json.dumps(arguments)))
                ]))])).encode())
                log = MemoryLog()
                with self.assertRaises((ValueError, ValidationError)):
                    ViewConversation(llm, log).propose(view, 'Tune rewards.',
                                                       SimulationConfiguration.defaults(), 'experiment')
                llm.complete.assert_called_once()
                self.assertEqual(log.events[-1]['name'], 'conversation_ended')
                self.assertEqual(log.events[-1]['log_level'], 'ERROR')
                self.assertIn('tool_execution_failed', [event['name'] for event in log.events])

    def test_prose_and_http_errors_do_not_trigger_retries(self):
        for status, body in ((200, b'{"choices":[{"message":{"content":"Done"}}]}'),
                             (503, b'Unavailable'), (200, b'not JSON')):
            with self.subTest(status=status, body=body):
                llm, log = Mock(url='http://local'), MemoryLog()
                llm.complete.return_value = status, '', body
                with self.assertRaises((ValueError, ValidationError, RuntimeError)):
                    ViewConversation(llm, log).propose(VIEWS['training'], 'Tune training.',
                                                       SimulationConfiguration.defaults(), 'experiment')
                llm.complete.assert_called_once()
                self.assertEqual(log.events[-1]['name'], 'conversation_ended')
