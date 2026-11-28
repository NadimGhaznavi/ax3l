"""Same-seed score history contains only the tuning view's parameter values."""

from copy import deepcopy
import json
import re
import unittest
from unittest.mock import patch

from ax3l.activity.ViewConfiguration import apply_values, historical_values, view_values
from ax3l.entities.ExperimentView import VIEWS
from ax3l.interface.SimulationConfiguration import SimulationConfiguration
from ax3l.presentation.ViewPrompts import ViewPrompts
from experiment_fixture import ExperimentFixture
from test_view_experiments import prompt_text
from view_cycle_fixtures import FakeSnake


def history_section(text):
    return text.split('## Historical Simulation Data\n', 1)[1].split('\n## ', 1)[0]


class HistoricalSimulationPromptTests(unittest.TestCase):
    def test_every_tuning_template_groups_all_runs_by_numeric_score_without_extra_text(self):
        config = SimulationConfiguration.defaults()
        changed = apply_values(config, {'training.batch_size': 32, 'model.hidden_size': 128,
                                        'epsilon.initial': .8, 'game.rewards.food': 20})
        runs = [dict(high_score=score, config=values) for score, values in (
            (9, config), (33, config), (0, config), (27, config), (33, changed), (33, config),
        )]
        original = deepcopy(runs)
        context = dict(
            previous_hypothesis='Previous hypothesis.', previous_values={},
            previous_observations='Previous observations.',
            rejected_hypothesis='Rejected hypothesis.', rejected_values={},
            reference_episodes=[], latest_episodes=[], reference_high_score=9, latest_high_score=33,
            parameters={}, other_parameters={},
        )
        with patch('ax3l.presentation.ViewPrompts.run_comparison_image', return_value='image'):
            prompts = ViewPrompts()
            for view in VIEWS.values():
                history = historical_values(view, runs)
                for no_history in (True, False):
                    for duplicate in (True, False):
                        with self.subTest(view=view.name, no_history=no_history, duplicate=duplicate):
                            content = prompts.render(view, dict(context, historical_simulation_data=history),
                                                     no_history=no_history, duplicate=duplicate)
                            section = history_section(content[0]['text'])
                            self.assertRegex(section, re.compile(r'\A\n```json\n.*\n```\n\Z', re.S))
                            data = json.loads(section.strip().removeprefix('```json\n').removesuffix('\n```'))
                            self.assertEqual(list(data), ['33', '27', '9', '0'])
                            self.assertEqual(data['33'], [view_values(view, config), view_values(view, changed),
                                                          view_values(view, config)])
                            for score in ('27', '9', '0'):
                                self.assertEqual(data[score], [view_values(view, config)])
                evaluation = prompts.render_evaluation(view, context)[0]['text']
                self.assertNotIn('## Historical Simulation Data', evaluation)
        self.assertEqual(runs, original)

    def test_empty_history_is_an_empty_json_object(self):
        self.assertEqual(historical_values(VIEWS['training'], []), {})


class HistoricalSimulationSelectionTests(ExperimentFixture):
    def test_selection_reads_all_scored_simulations_for_the_current_seed(self):
        self.snake = FakeSnake((999, 33, 9, 33, 0, 5, 10, 8))
        config = SimulationConfiguration.defaults()
        foreign = deepcopy(config)
        foreign['seed'] += 1
        self.snake.submit_simulation(foreign)
        for initial in (.7, .6, .5, .4, .3):
            run_id = self.snake.submit_simulation(apply_values(config, {'epsilon.initial': initial}))
        self.snake.results[run_id]['high_score'] = None
        self.loop().run(cycles=1)
        data = json.loads(history_section(prompt_text(self.model.requests[0])).strip()
                          .removeprefix('```json\n').removesuffix('\n```'))
        self.assertEqual(list(data), ['33', '10', '9', '0'])
        view = VIEWS['exploration']
        self.assertEqual(data['33'], [
            view_values(view, apply_values(config, {'epsilon.initial': .7})),
            view_values(view, apply_values(config, {'epsilon.initial': .5})),
        ])
        self.assertEqual(data['10'], [view_values(view, config)])
        self.assertEqual(data['9'], [view_values(view, apply_values(config, {'epsilon.initial': .6}))])
        self.assertEqual(data['0'], [view_values(view, apply_values(config, {'epsilon.initial': .4}))])
        self.assertNotIn('## Historical Simulation Data', prompt_text(self.model.requests[1]))
