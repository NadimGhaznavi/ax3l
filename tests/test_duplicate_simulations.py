"""Duplicate candidates return to their owning view before any run is submitted."""

from copy import deepcopy
import json
from unittest.mock import patch

from ax3l.activity.ViewConfiguration import view_values
from ax3l.entities.ExperimentState import ExperimentState
from ax3l.entities.ExperimentView import VIEWS
from ax3l.entities.ViewProposal import ViewProposal
from ax3l.interface.SimulationConfiguration import SimulationConfiguration
from experiment_fixture import ExperimentFixture
from test_view_experiments import prompt_text
from view_cycle_fixtures import FakeSnake


class DuplicateSimulationTests(ExperimentFixture):
    def ready(self, name):
        config = SimulationConfiguration.defaults()
        run_id = self.snake.submit_simulation(config)
        self.log.log('golden_config_created', 'Configuration', 'INFO', 'Baseline.', process_id=run_id)
        state = ExperimentState('duplicate', 'ready', deepcopy(config), golden_run_id=run_id,
                                reference_run_id=run_id, latest_run_id=run_id, order=list(VIEWS),
                                view_index=list(VIEWS).index(name),
                                proposals={name: ViewProposal('Rejected hypothesis.', view_values(VIEWS[name], config))})
        self.store.save(state)
        return state

    def test_all_views_revise_their_own_duplicate_and_keep_other_settings(self):
        for name in VIEWS:
            with self.subTest(view=name):
                self.snake = FakeSnake((10, 12))
                self.log.events.clear()
                self.model.requests.clear()
                state = self.ready(name)
                self.loop().run(cycles=1)
                request = self.model.requests[0]
                text = prompt_text(request)
                self.assertTrue(text.startswith('This configuration is a duplicate,'))
                self.assertIn('Rejected hypothesis.', text)
                self.assertIn('Baseline Results', text)
                self.assertEqual(set(self.store.load().proposals), {name})
                self.assertEqual(self.store.load().view_index, state.view_index)
                proposal = self.store.load().proposals[name]
                for other in VIEWS.values():
                    for path, value in view_values(other, state.config).items():
                        if path not in VIEWS[name].parameters:
                            self.assertEqual(view_values(other, self.store.load().config)[path], value)
                self.assertTrue(set(proposal.values) <= set(VIEWS[name].parameters))
                self.assertEqual(len(self.snake.submissions), 2)
                self.assertEqual(self.store.load().failures, 0)

    def test_restart_preserves_the_view_and_notice_without_reshuffling(self):
        self.ready('architecture')
        save = self.store.save
        def stop(state):
            save(state)
            if state.phase == 'revising':
                raise KeyboardInterrupt()
        with patch.object(self.store, 'save', side_effect=stop):
            with self.assertRaises(KeyboardInterrupt):
                self.loop().run(cycles=1)
        self.assertEqual(self.model.requests, [])
        self.loop().run(cycles=1)
        self.shuffle.assert_not_called()
        self.assertIn('Architecture Tuning', prompt_text(self.model.requests[0]))
        self.assertEqual(len(self.snake.submissions), 2)

    def test_a_second_duplicate_is_revised_without_counting_a_failed_simulation(self):
        original = self.ready('training')
        respond = self.model.respond
        def unchanged(request):
            response = respond(request)
            if len(self.model.requests) == 1:
                function = response['choices'][0]['message']['tool_calls'][0]['function']
                function['arguments'] = json.dumps(dict(hypothesis='Keep settings.',
                                                       values=original.proposals['training'].values))
            return response
        self.model.respond = unchanged
        self.loop().run(cycles=1)
        self.assertEqual(len(self.model.requests), 3)
        self.assertEqual(len(self.snake.submissions), 2)
        self.assertEqual(self.event_count('configuration_compared'), 1)
