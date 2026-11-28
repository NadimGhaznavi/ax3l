"""Exercise the view cycle through real prompt rendering and local HTTP inference."""

from collections import Counter
from copy import deepcopy
import json
import re
import unittest
from unittest.mock import Mock, patch

from jsonschema import ValidationError

from ax3l.activity.ViewConfiguration import apply_values, other_parameters
from ax3l.constants.DViewConversation import DViewConversation
from ax3l.entities.ExperimentView import VIEWS
from ax3l.entities.ExperimentState import ExperimentState
from ax3l.interface.SimulationConfiguration import SCHEMA, SimulationConfiguration
from ax3l.interface.ViewConversation import ViewConversation
from experiment_fixture import ExperimentFixture
from view_cycle_fixtures import FakeSnake, MemoryLog


def prompt_text(request):
    content = request['messages'][0]['content']
    return content if isinstance(content, str) else '\n'.join(
        part['text'] for part in content if part['type'] == 'text')


def blocks(request):
    content = prompt_text(request).split('## Submit your')[0]
    return [json.loads(block) for block in re.findall(r'```json\n(.*?)\n```', content, re.S)]


def tool_name(request):
    return request['tools'][0]['function']['name']


class ProposalBoundaryTests(unittest.TestCase):
    def response(self, name, arguments):
        return json.dumps(dict(choices=[dict(message=dict(tool_calls=[
            dict(function=dict(name=name, arguments=json.dumps(arguments)))
        ]))])).encode()

    def test_observations_are_required_short_text_and_cannot_propose_settings(self):
        for arguments in ({'observations': ''}, {'observations': '  '}, {'observations': 7}, {},
                          {'observations': 'x' * (DViewConversation.OBSERVATIONS_MAX_LENGTH + 1)},
                          {'observations': 'Done.', 'values': {'seed': 12}}):
            with self.subTest(arguments=arguments):
                llm, log = Mock(url='http://local'), MemoryLog()
                llm.complete.return_value = 200, '', self.response('submit_observations', arguments)
                with self.assertRaises(ValidationError):
                    ViewConversation(llm, log).evaluate(VIEWS['training'], [], 'experiment')
                llm.complete.assert_called_once()
                self.assertEqual(log.events[-1]['name'], 'conversation_ended')
                self.assertEqual(log.events[-1]['log_level'], 'ERROR')
                self.assertIn('tool_execution_failed', [event['name'] for event in log.events])

    def test_both_text_fields_accept_the_exact_character_limit(self):
        llm, log = Mock(url='http://local'), MemoryLog()
        text = 'x' * DViewConversation.OBSERVATIONS_MAX_LENGTH
        llm.complete.return_value = 200, '', self.response('submit_observations', dict(observations=text))
        conversation = ViewConversation(llm, log)
        self.assertEqual(conversation.evaluate(VIEWS['training'], [], 'experiment'), text)
        hypothesis = 'x' * DViewConversation.HYPOTHESIS_MAX_LENGTH
        llm.complete.return_value = 200, '', self.response('submit_view', dict(
            hypothesis=hypothesis, values={'training.gamma': .95}))
        result = conversation.propose(VIEWS['training'], 'Tune training.', 'experiment')
        self.assertEqual(result.hypothesis, hypothesis)

    def test_simulation_values_are_left_for_snakelab_to_validate(self):
        for values in (
            {'game.rewards.closer_to_food': 5, 'game.rewards.further_from_food': -1},
            {'game.rewards.closer_to_food': 5},
            {'game.rewards.further_from_food': 0},
            {'game.rewards.food': 21},
            {'game.rewards.food': True},
        ):
            with self.subTest(values=values):
                llm, log = Mock(url='http://local'), MemoryLog()
                arguments = dict(hypothesis='Test reward signals.', values=values)
                llm.complete.return_value = 200, '', self.response('submit_view', arguments)
                result = ViewConversation(llm, log).propose(VIEWS['reward-signals'], 'Tune rewards.', 'experiment')
                self.assertEqual(result.values, values)
                self.assertEqual(log.events[-1]['log_level'], 'INFO')
                llm.complete.assert_called_once()

    def test_evaluation_rejects_a_configuration_submission(self):
        llm, log = Mock(url='http://local'), MemoryLog()
        llm.complete.return_value = 200, '', self.response('submit_view', dict(
            hypothesis='A better score.', values={'training.gamma': .95}))
        with self.assertRaises(ValidationError):
            ViewConversation(llm, log).evaluate(VIEWS['training'], [], 'experiment')
        llm.complete.assert_called_once()

    def test_invalid_tool_results_are_rejected_once_and_conversations_always_end(self):
        view = VIEWS['reward-signals']
        template = dict(hypothesis='Test rewards.',
                        values={'game.rewards.food': 12})
        cases = [
            dict(template, values={'game.rewards.food': float('nan')}),
            dict(template, values={'training.sequence_length': 8}),
            dict(template, hypothesis='  '),
            dict(template, hypothesis='x' * (DViewConversation.HYPOTHESIS_MAX_LENGTH + 1)),
            dict(template, evaluation='Evaluation belongs in its own conversation.'),
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
                    ViewConversation(llm, log).propose(view, 'Tune rewards.', 'experiment')
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
                    ViewConversation(llm, log).propose(VIEWS['training'], 'Tune training.', 'experiment')
                llm.complete.assert_called_once()
                self.assertEqual(log.events[-1]['name'], 'conversation_ended')


class ViewConfigurationTests(unittest.TestCase):
    def test_views_cover_tunable_fields_and_share_only_sequence_length_and_gamma(self):
        def fields(schema, prefix=''):
            for key, value in schema['properties'].items():
                name = f'{prefix}.{key}' if prefix else key
                if value['type'] == 'object':
                    yield from fields(value, name)
                elif 'const' not in value:
                    yield name
        editable = [path for view in VIEWS.values() for path in view.parameters]
        self.assertEqual(set(editable), set(fields(SCHEMA)) - {'seed'})
        self.assertEqual({path for path, count in Counter(editable).items() if count > 1},
                         {'training.sequence_length', 'training.gamma'})
        config = SimulationConfiguration.defaults()
        original = deepcopy(config)
        readonly = other_parameters(VIEWS['training'], config)
        self.assertEqual(readonly['seed'], config['seed'])
        self.assertNotIn('learning_rate', readonly['training'])
        self.assertEqual(apply_values(config, {'model.layers': 2})['model']['layers'], 2)
        self.assertEqual(config, original)


class ViewCycleTests(ExperimentFixture):
    def test_each_view_submits_and_evaluates_before_the_next_view(self):
        self.loop().run(cycles=4)
        self.assertEqual([tool_name(r) for r in self.model.requests],
                         ['submit_view', 'submit_observations'] * 4)
        self.assertEqual(len(self.snake.submissions), 5)
        self.assertEqual(self.snake.submissions[0], SimulationConfiguration.defaults())
        self.shuffle.assert_called_once()
        for index, name in enumerate(reversed(VIEWS)):
            request = self.model.requests[index * 2]
            parameters, readonly = blocks(request)
            self.assertEqual(set(parameters), set(VIEWS[name].parameters))
            self.assertNotIn('new seed', parameters)
            self.assertIn('Baseline Results', prompt_text(request))
            self.assertNotIn('Previous hypothesis', prompt_text(request))
            self.assertNotIn('(draft)', json.dumps(readonly))
            proposal = json.loads([e['content'] for e in self.log.events
                                   if e['name'] == 'tool_execution_completed'][index * 2])
            self.assertEqual(self.snake.submissions[index + 1], apply_values(
                self.snake.submissions[0], proposal['values']))
        self.loop().run(cycles=1)
        self.assertEqual(self.shuffle.call_count, 2)
        self.assertEqual(self.store.load().view_index, 0)

    def test_only_current_golden_owner_gets_history_even_after_a_losing_attempt(self):
        self.snake = FakeSnake((10, 12, 9, 9, 9, 9, 12, 9, 9, 9))
        self.loop().run(cycles=5)
        history = self.store.load().golden_history
        self.assertEqual(history.view, 'exploration')
        owner_request = self.model.requests[8]
        self.assertIn('Previous hypothesis', prompt_text(owner_request))
        reference_score = self.snake.results[history.reference_run_id]['high_score']
        latest_score = self.snake.results[history.latest_run_id]['high_score']
        self.assertIn(f'- Golden high score: {reference_score}', prompt_text(owner_request))
        self.assertIn(f'- Latest high score: {latest_score}', prompt_text(owner_request))
        self.assertNotIn(history.reference_run_id, prompt_text(owner_request))
        self.assertNotIn(history.latest_run_id, prompt_text(owner_request))
        self.assertIn(history.observations, prompt_text(owner_request))
        for index in (2, 4, 6):
            self.assertIn('Baseline Results', prompt_text(self.model.requests[index]))
        # Training ties the golden and takes ownership; Exploration loses its history.
        self.loop().run(cycles=4)
        self.assertEqual(self.store.load().golden_history.view, 'training')
        self.assertIn('Baseline Results', prompt_text(self.model.requests[-2]))
        self.assertEqual(self.store.load().golden_history.latest_run_id, list(self.snake.results)[6])

    def test_tie_promotes_candidate_and_resets_failures(self):
        self.snake = FakeSnake((10, 9, 10))
        self.loop().run(cycles=1)
        self.assertEqual(self.store.load().failures, 1)
        self.loop().run(cycles=1)
        state = self.store.load()
        self.assertEqual(state.golden_run_id, state.run_id)
        self.assertEqual(state.failures, 0)
        self.assertEqual(state.golden_history.view, 'training')
        self.assertEqual(self.event_count('golden_config_created'), 2)

    def test_new_view_uses_latest_golden_and_can_retune_shared_parameters(self):
        self.snake = FakeSnake((10, 11, 12, 13, 14))
        self.loop().run(cycles=4)
        for index in range(1, 4):
            prior = self.snake.submissions[index]
            current = self.snake.submissions[index + 1]
            request = self.model.requests[2 * index]
            reference_score = list(self.snake.results.values())[index]['high_score']
            self.assertIn(f'- Baseline high score: {reference_score}', prompt_text(request))
            if index == 2:  # Architecture follows Training and can tune sequence_length again.
                self.assertEqual(blocks(request)[0]['training.sequence_length']['value'],
                                 prior['training']['sequence_length'])
                self.assertIn('training.sequence_length', request['tools'][0]['function'][
                    'parameters']['properties']['values']['properties'])
            self.assertEqual(current['seed'], prior['seed'])

    def test_existing_golden_is_reused_without_fake_hypotheses_or_evaluations(self):
        run_id = self.snake.submit_simulation(SimulationConfiguration.defaults())
        self.log.log('golden_config_created', 'Configuration', 'INFO', 'Existing.', process_id=run_id)
        self.loop().run(cycles=1)
        self.assertEqual(len(self.snake.submissions), 2)
        self.assertIn('- Baseline high score: 10', prompt_text(self.model.requests[0]))
        self.assertNotIn(run_id, prompt_text(self.model.requests[0]))
        self.assertEqual(tool_name(self.model.requests[0]), 'submit_view')

    def test_old_snakelab_history_does_not_replace_the_default_baseline(self):
        old = self.snake.submit_simulation(apply_values(SimulationConfiguration.defaults(), {'model.layers': 3}))
        self.snake.results[old]['high_score'] = 999
        self.loop().run(cycles=1)
        self.assertEqual(self.snake.submissions[1], SimulationConfiguration.defaults())
        baseline_score = list(self.snake.results.values())[1]['high_score']
        self.assertIn(f'- Baseline high score: {baseline_score}', prompt_text(self.model.requests[0]))

    def test_restarts_keep_order_and_do_not_repeat_accepted_selection_or_evaluation(self):
        save = self.store.save
        def stop(state):
            save(state)
            if state.phase == 'ready' and state.proposals:
                raise KeyboardInterrupt()
        with patch.object(self.store, 'save', side_effect=stop):
            with self.assertRaises(KeyboardInterrupt):
                self.loop().run(cycles=1)
        self.assertEqual(len(self.model.requests), 1)
        order = self.store.load().order
        self.loop().run(cycles=1)
        self.assertEqual(len(self.model.requests), 2)
        self.assertEqual(len(self.snake.submissions), 2)
        self.loop().run(cycles=1)
        self.assertEqual(self.store.load().order, order)
        self.assertEqual(self.store.load().view_index, 1)
        self.shuffle.assert_called_once()

    def test_comparison_replay_does_not_count_failure_or_promote_twice(self):
        for score in (9, 10, 11):
            with self.subTest(score=score):
                self.log.events.clear()
                self.store.state = None
                self.model.requests.clear()
                self.snake = FakeSnake((10, score))
                save = self.store.save
                def stop(state):
                    if state.phase == 'evaluating':
                        raise KeyboardInterrupt()
                    save(state)
                with patch.object(self.store, 'save', side_effect=stop):
                    with self.assertRaises(KeyboardInterrupt):
                        self.loop().run(cycles=1)
                self.assertEqual(self.store.load().phase, 'comparing')
                self.loop().run(cycles=1)
                self.assertEqual(self.event_count('configuration_compared'), 1)
                self.assertEqual(self.event_count('golden_config_created'), 1 + (score >= 10))
                self.assertEqual(self.store.load().failures, int(score < 10))
                self.assertEqual(len(self.snake.submissions), 2)

    def test_lost_submission_reply_is_reconciled_without_resubmitting(self):
        submit = self.snake.submit_simulation
        for boundary in (1, 2):
            with self.subTest(boundary=boundary):
                self.log.events.clear()
                self.store.state = None
                self.snake = FakeSnake((10, 9))
                submit = self.snake.submit_simulation
                def lost(config):
                    run_id = submit(config)
                    if len(self.snake.submissions) == boundary:
                        raise TimeoutError('Lost reply')
                    return run_id
                with patch.object(self.snake, 'submit_simulation', side_effect=lost):
                    with self.assertRaises(TimeoutError):
                        self.loop().run(cycles=1)
                self.assertEqual(self.store.load().phase, 'submitting')
                self.loop().run(cycles=1)
                self.assertEqual(len(self.snake.submissions), 2)

    def test_unresolved_or_old_matching_submission_is_never_retried(self):
        config = SimulationConfiguration.defaults()
        old = self.snake.submit_simulation(config)
        self.store.save(ExperimentState('baseline-attempt', 'ready', config, baseline=True))
        with patch.object(self.snake, 'submit_simulation', side_effect=TimeoutError('No reply')) as submit:
            with self.assertRaises(TimeoutError):
                self.loop().run(cycles=1)
            self.assertEqual(self.store.load().preceding_match, old)
            with self.assertRaisesRegex(RuntimeError, 'will not be retried'):
                self.loop().run(cycles=1)
            submit.assert_called_once()

    def test_failed_run_blocks_progress_and_resumes_without_resubmission(self):
        submit = self.snake.submit_simulation
        def fail(config):
            run_id = submit(config)
            if len(self.snake.submissions) == 2:
                self.snake.results[run_id]['status'] = 'failed'
            return run_id
        with patch.object(self.snake, 'submit_simulation', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'failed'):
                self.loop().run(cycles=1)
        self.assertEqual(len(self.model.requests), 1)
        self.assertEqual(self.store.load().failures, 0)
        self.snake.results[self.store.load().run_id]['status'] = 'completed'
        self.loop().run(cycles=1)
        self.assertEqual(len(self.snake.submissions), 2)
        self.assertEqual(len(self.model.requests), 2)

    def test_invalid_observations_retry_only_the_unaccepted_evaluation(self):
        respond = self.model.respond
        def invalid(request):
            response = respond(request)
            if tool_name(request) == 'submit_observations':
                response['choices'][0]['message']['tool_calls'][0]['function']['arguments'] = '{}'
            return response
        self.model.respond = invalid
        with self.assertRaises(ValidationError):
            self.loop().run(cycles=1)
        self.assertEqual(self.store.load().phase, 'evaluating')
        self.model.respond = respond
        self.loop().run(cycles=1)
        self.assertEqual(len(self.snake.submissions), 2)
        self.assertEqual(len(self.model.requests), 3)
