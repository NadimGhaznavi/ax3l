"""Ax3l's experiment policy remains compatible with Snake Lab 3.0.1."""

import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, ValidationError

from ax3l.interface.SimulationConfiguration import SimulationConfiguration
from ax3l.app.snakelab.ParameterSpace import finite_choices


class SimulationPolicyTests(unittest.TestCase):
    def test_required_defaults_and_independent_resolutions(self):
        config = SimulationConfiguration.defaults()
        self.assertEqual(config['epochs'], 500)
        self.assertEqual(config['model']['type'], 'transformer')
        self.assertEqual(config['model']['heads'], 4)
        self.assertEqual(config['epsilon_nice'], {'probability': .005, 'steps': 20})
        self.assertEqual(config['epsilon'], {'initial': .96, 'minimum': 0, 'decay': .97})
        config['epsilon_nice']['probability'] = 0
        self.assertEqual(SimulationConfiguration.defaults()['epsilon_nice']['probability'], .005)

    def test_fixed_architecture_duration_and_required_nice(self):
        for path, value in ((('model', 'type'), 'rnn'), (('model', 'heads'), 8),
                            (('epochs',), 1500), (('epsilon_nice', 'probability'), 0)):
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

    def test_every_legal_reward_pair_is_accepted_by_the_released_server_schema(self):
        root = Path(__file__).resolve().parents[1]
        upstream = Draft202012Validator(json.loads(
            (root / 'pages/snake-lab/simulation-config-v2.schema.json').read_text()))
        config = SimulationConfiguration.defaults()
        upstream.validate(config)
        for closer, further in finite_choices('reward_pair'):
            config['game']['rewards'].update(closer_to_food=float(closer), further_from_food=float(further))
            SimulationConfiguration.validate(config)
            upstream.validate(config)
        for probability, steps in ((.0001, 1), (.01, 40), (1, 1000)):
            config['epsilon_nice'].update(probability=probability, steps=steps)
            SimulationConfiguration.validate(config)
            upstream.validate(config)

    def test_positive_reward_loops_and_nonfinite_proposals_are_rejected(self):
        config = SimulationConfiguration.defaults()
        config['game']['rewards'].update(closer_to_food=6, further_from_food=0)
        with self.assertRaisesRegex(ValidationError, 'rewarding loops'):
            SimulationConfiguration.validate(config)
        for value in (True, '.01', float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                SimulationConfiguration.value(('epsilon_nice', 'probability'), value)
