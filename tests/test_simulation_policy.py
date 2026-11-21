"""Ax3l's experiment policy remains compatible with the bundled Snake Lab schema."""

import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, ValidationError

from ax3l.interface.SimulationConfiguration import SimulationConfiguration
from ax3l.app.snakelab.ParameterSpace import finite_choices


class SimulationPolicyTests(unittest.TestCase):
    def test_required_defaults_and_independent_resolutions(self):
        config = SimulationConfiguration.defaults()
        self.assertEqual(config['epochs'], 750)
        self.assertEqual(config['model']['type'], 'transformer')
        self.assertEqual(config['model']['heads'], 4)
        self.assertEqual(config['model']['hidden_size'], 64)
        self.assertEqual(config['model']['layers'], 1)
        self.assertEqual(config['model']['dropout'], .05)
        self.assertEqual(config['epsilon_nice'], {'probability': .05, 'steps': 20})
        self.assertEqual(config['epsilon'], {'initial': .96, 'minimum': 0, 'decay': .97})
        self.assertEqual({key: config['game']['rewards'][key] for key in ('empty', 'snake', 'wall')},
                         {'empty': 0, 'snake': -10, 'wall': -10})
        config['epsilon_nice']['probability'] = 0
        self.assertEqual(SimulationConfiguration.defaults()['epsilon_nice']['probability'], .05)

    def test_fixed_architecture_duration_and_required_nice(self):
        for path, value in ((('model', 'type'), 'rnn'), (('model', 'heads'), 8),
                            (('training', 'tau'), .001),
                            (('epochs',), 500), (('epsilon_nice', 'probability'), 0)):
            config = SimulationConfiguration.defaults()
            node = config
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(ValidationError):
                SimulationConfiguration.validate(config)
        config = SimulationConfiguration.defaults()
        config['epsilon']['decay'] = .999
        SimulationConfiguration.validate(config)

    def test_every_tunable_model_value_is_accepted_by_the_server_schema(self):
        root = Path(__file__).resolve().parents[1]
        upstream = Draft202012Validator(json.loads(
            (root / 'pages/snake-lab/simulation-config-v2.schema.json').read_text()))
        config = SimulationConfiguration.defaults()
        for field in ('hidden_size', 'layers', 'dropout'):
            for (value,) in finite_choices(field):
                value = float(value) if field == 'dropout' else int(value)
                with self.subTest(field=field, value=value):
                    self.assertEqual(SimulationConfiguration.value(('model', field), value), value)
                    config['model'][field] = value
                    SimulationConfiguration.validate(config)
                    upstream.validate(config)

    def test_every_legal_reward_pair_is_accepted_by_the_server_schema(self):
        root = Path(__file__).resolve().parents[1]
        upstream = Draft202012Validator(json.loads(
            (root / 'pages/snake-lab/simulation-config-v2.schema.json').read_text()))
        config = SimulationConfiguration.defaults()
        upstream.validate(config)
        for closer, further in finite_choices('reward_pair'):
            config['game']['rewards'].update(closer_to_food=float(closer), further_from_food=float(further))
            SimulationConfiguration.validate(config)
            upstream.validate(config)
        for probability, steps in ((.0001, 1), (.01, 20), (.1, 40)):
            config['epsilon_nice'].update(probability=probability, steps=steps)
            SimulationConfiguration.validate(config)
            upstream.validate(config)

    def test_epsilon_nice_limits_apply_to_field_choices_and_complete_configurations(self):
        for probability, steps in ((.0001, 1), (.05, 20), (.1, 40)):
            with self.subTest(probability=probability, steps=steps):
                self.assertEqual(SimulationConfiguration.value(('epsilon_nice', 'probability'), probability), probability)
                self.assertEqual(SimulationConfiguration.value(('epsilon_nice', 'steps'), steps), steps)
                config = SimulationConfiguration.defaults()
                config['epsilon_nice'].update(probability=probability, steps=steps)
                SimulationConfiguration.validate(config)
        for field, values in (('probability', (0, .100001, .11, 1)), ('steps', (0, 41, 60, 1000))):
            for value in values:
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValidationError):
                        SimulationConfiguration.value(('epsilon_nice', field), value)
                    config = SimulationConfiguration.defaults()
                    config['epsilon_nice'][field] = value
                    with self.assertRaises(ValidationError) as error:
                        SimulationConfiguration.validate(config)
                    self.assertEqual(list(error.exception.absolute_path), ['epsilon_nice', field])

    def test_positive_reward_loops_and_nonfinite_proposals_are_rejected(self):
        config = SimulationConfiguration.defaults()
        config['game']['rewards'].update(closer_to_food=5, further_from_food=0)
        with self.assertRaisesRegex(ValidationError, 'rewarding loops'):
            SimulationConfiguration.validate(config)
        for value in (True, '.01', float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                SimulationConfiguration.value(('epsilon_nice', 'probability'), value)

    def test_move_and_collision_rewards_accept_boundaries_and_fractional_values(self):
        for field, values in (('empty', (-2, -1.25, 0, .25, 2)),
                              ('snake', (-20, -2.5, 0)), ('wall', (-20, -2.5, 0))):
            for value in values:
                with self.subTest(field=field, value=value):
                    path = ('game', 'rewards', field)
                    self.assertEqual(SimulationConfiguration.value(path, value), value)
                    config = SimulationConfiguration.defaults()
                    config['game']['rewards'][field] = value
                    SimulationConfiguration.validate(config)

    def test_reward_limits_apply_to_choices_and_complete_configurations(self):
        for field, values in (('empty', (-2.001, 2.001)),
                              ('snake', (-20.001, .001)), ('wall', (-20.001, .001)),
                              ('food', (5,)), ('max_moves', (-5,))):
            for value in values:
                with self.subTest(field=field, value=value):
                    path = ('game', 'rewards', field)
                    with self.assertRaises(ValidationError):
                        SimulationConfiguration.value(path, value)
                    config = SimulationConfiguration.defaults()
                    config['game']['rewards'][field] = value
                    with self.assertRaises(ValidationError) as error:
                        SimulationConfiguration.validate(config)
                    self.assertEqual(tuple(error.exception.absolute_path), path)
