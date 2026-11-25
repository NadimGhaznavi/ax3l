import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from ax3l.interface.SimulationConfiguration import SimulationConfiguration


ROOT = Path(__file__).resolve().parents[1]


class DefaultConfigTests(unittest.TestCase):
    def test_defaults_form_a_valid_complete_configuration(self):
        schema = json.loads((ROOT / "ax3l/interface/schemas/simulation-config-v2.schema.json").read_text())
        config = SimulationConfiguration.defaults()
        Draft202012Validator(schema).validate(config)
        self.assertEqual(config["model"], {
            "type": "transformer", "heads": 4, "hidden_size": 64, "layers": 1, "dropout": 0.05,
        })
        self.assertEqual(config["training"], {
            "sequence_length": 4, "batch_size": 64, "replay_max_frames": 100000,
            "learning_rate": 0.001, "gamma": 0.96, "tau": 0.05, "max_gradient_norm": 1.0,
        })
        self.assertEqual(config["game"]["rewards"]["wall"], -10)
        config["training"]["batch_size"] = 8
        self.assertEqual(SimulationConfiguration.defaults()["training"]["batch_size"], 64)
