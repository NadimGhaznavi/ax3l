import copy
import sqlite3
import unittest
from fractions import Fraction

from ax3l.app.snakelab.ParameterSpace import finite_choices, finite_values
from ax3l.app.snakelab.GenerateDefaultConfig import GenerateDefaultConfig
from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb, CONFIGURATION_FIELDS, _config_values


class ParameterSpaceTests(unittest.TestCase):
    def test_schema_domains(self):
        self.assertEqual(finite_choices('sequence_length'), {(n,) for n in range(4, 49, 4)})
        self.assertEqual(len(finite_choices('hidden_size')), 21)
        self.assertEqual(len(finite_choices('batch_size')), 29)
        self.assertEqual(finite_choices('reward_pair'), {(a, b) for a in range(7) for b in range(-6, 1)})
        for parameter in ('learning_rate', 'gamma', 'epsilon_pair'):
            self.assertIsNone(finite_choices(parameter))

    def test_exclusive_bounds_decimal_steps_and_enum(self):
        self.assertEqual(finite_values({'type': 'number', 'exclusiveMinimum': .1,
                                       'exclusiveMaximum': .4, 'multipleOf': .1}),
                         (Fraction(1, 5), Fraction(3, 10)))
        self.assertEqual(finite_values({'type': 'integer', 'minimum': 1,
                                       'maximum': 8, 'multipleOf': 1.5}), (3, 6))
        self.assertEqual(finite_values({'type': 'integer', 'enum': [2, 8]}), (2, 8))


class ExhaustionDbTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        self.addCleanup(self.connection.close)
        columns = ', '.join(f'{column} NUMERIC' for column, _, _ in CONFIGURATION_FIELDS)
        self.connection.execute(f'CREATE TABLE configurations (run_id TEXT, {columns})')
        self.connection.execute('CREATE TABLE simulation_runs (run_id TEXT, status TEXT)')
        self.snake = SnakeLabDb(self)
        self.base = GenerateDefaultConfig().run()
        self.insert('gold', self.base)

    def query(self, sql, params):
        return [dict(row) for row in self.connection.execute(sql.replace('%s', '?'), params)]

    def insert(self, run_id, config, status='completed'):
        values = (run_id,) + _config_values(config)
        self.connection.execute('INSERT INTO configurations VALUES (' + ','.join('?' for _ in values) + ')', values)
        self.connection.execute('INSERT INTO simulation_runs VALUES (?, ?)', (run_id, status))

    def test_sequence_exhaustion_uses_current_seed_and_matching_settings(self):
        for n in range(4, 49, 4):
            config = copy.deepcopy(self.base)
            config['training']['sequence_length'] = n
            self.insert(f'run-{n}', config, 'failed' if n == 4 else 'completed')
        self.assertTrue(self.snake.parameter_space_exhausted('gold', 'sequence_length'))
        for name, change in [('seed', lambda c: c.update(seed=c['seed'] + 1)),
                             ('settings', lambda c: c['training'].update(batch_size=32))]:
            config = copy.deepcopy(self.base)
            change(config)
            self.insert(name, config)
            self.assertFalse(self.snake.parameter_space_exhausted(name, 'sequence_length'))
        self.connection.execute("DELETE FROM simulation_runs WHERE run_id='run-48'")
        # An out-of-range value must not fill the missing legal choice.
        config = copy.deepcopy(self.base)
        config['training']['sequence_length'] = 52
        self.insert('invalid-history', config)
        self.assertFalse(self.snake.parameter_space_exhausted('gold', 'sequence_length'))

    def test_reward_grid_requires_every_pair(self):
        for a in range(7):
            for b in range(-6, 1):
                if (a, b) == (6, 0):
                    continue
                config = copy.deepcopy(self.base)
                config['game']['rewards'].update(closer_to_food=a, further_from_food=b)
                self.insert(f'{a}:{b}', config)
        self.assertFalse(self.snake.parameter_space_exhausted('gold', 'reward_pair'))
        config['game']['rewards'].update(closer_to_food=6, further_from_food=0)
        self.insert('last', config)
        self.assertTrue(self.snake.parameter_space_exhausted('gold', 'reward_pair'))
