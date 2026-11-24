"""Run with AX3L_TEST_DB=1 and the disposable test DB_* credentials."""

import os
from fractions import Fraction
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from ax3l.app.DbMgr import DbMgr
from ax3l.interface.SnakeLab import SnakeLab
from ax3l.interface.SimulationConfiguration import SimulationConfiguration
from ax3l.app.snakelab.SnakeLabDb import CONFIGURATION_COLUMNS, CONFIGURATION_FIELDS, _config_values


@unittest.skipUnless(os.environ.get("AX3L_TEST_DB") == "1", "requires disposable MariaDB test database")
class SnakeLabDbTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ["DB_NAME"], "ax3l_test")
        initialization = patch.object(
            DbMgr, "_initialize_event_tables",
            side_effect=AssertionError("External connections must not initialize tables"),
        )
        initialization.start()
        self.addCleanup(initialization.stop)

    def query_count(self, statuses=()):
        def connect(**kwargs):
            self.assertEqual(kwargs.pop("database"), "snakelab")
            db = DbMgr(**kwargs)
            self.addCleanup(lambda: db.close() if db._connection.open else None)
            self.db = db
            schema = (Path(__file__).resolve().parents[1] /
                      "pages/snake-lab/database-v1.sql").read_text().split(";", 1)[0]
            schema = schema.replace("CREATE TABLE IF NOT EXISTS", "CREATE TEMPORARY TABLE")
            # v2 removes configuration uniqueness; retain it only by run_id.
            schema = schema.replace(
                "    UNIQUE KEY uq_simulation_experiment (project_version, config_hash),\n", ""
            )
            db.execute(schema)
            for status in statuses:
                db.execute(
                    """INSERT INTO simulation_runs
                       (run_id, project_version, config_hash, status)
                       VALUES (%s, %s, %s, %s)""",
                    (str(uuid4()), "test", "a" * 64, status),
                )
            return db

        with patch("ax3l.interface.SnakeLab.DbMgr", side_effect=connect) as factory:
            try:
                return SnakeLab().get_num_sims()
            finally:
                factory.assert_called_once_with(
                    database="snakelab", initialize_event_tables=False
                )

    def test_empty_database(self):
        self.assertEqual(self.query_count(), 0)
        self.assertFalse(self.db._connection.open)

    def test_high_score_across_runs_and_seeds_through_interface(self):
        def connect(**kwargs):
            self.assertEqual(kwargs.pop("database"), "snakelab")
            db = DbMgr(**kwargs)
            self.db = db
            self.addCleanup(lambda: db.close() if db._connection.open else None)
            db.execute("""CREATE TEMPORARY TABLE simulation_runs (
                status VARCHAR(16), high_score INT NULL
            )""")
            for config, status, score in rows:
                db.execute("INSERT INTO simulation_runs VALUES (%s, %s)",
                           (status, score))
            return db

        cases = [
            ([], None),
            ([("{}", "queued", None)], None),
            ([("{}", "completed", 0)], 0),
            ([("{\"seed\": 1}", "completed", 55),
              ("{\"seed\": 2}", "completed", 40),
              ("{}", "queued", None)], 55),
            ([("{}", "completed", 40), ("{}", "running", 55)], 55),
        ]
        for rows, expected in cases:
            with self.subTest(rows=rows):
                with patch("ax3l.interface.SnakeLab.DbMgr", side_effect=connect) as factory:
                    self.assertEqual(SnakeLab().get_high_score(), expected)
                factory.assert_called_once_with(database="snakelab", initialize_event_tables=False)
                self.assertFalse(self.db._connection.open)

    def test_episode_losses_are_scoped_ordered_and_preserve_nulls(self):
        run_id, other_run = str(uuid4()), str(uuid4())

        def connect(**kwargs):
            self.assertEqual(kwargs.pop("database"), "snakelab")
            db = DbMgr(**kwargs)
            self.db = db
            self.addCleanup(lambda: db.close() if db._connection.open else None)
            db.execute("""CREATE TEMPORARY TABLE simulation_episodes (
                run_id CHAR(36) NOT NULL, episode INT UNSIGNED NOT NULL,
                loss DOUBLE NULL, PRIMARY KEY (run_id, episode)
            )""")
            for episode, loss in ((3, 0.0), (1, None), (2, 0.5)):
                db.execute("INSERT INTO simulation_episodes VALUES (%s, %s, %s)",
                           (run_id, episode, loss))
            db.execute("INSERT INTO simulation_episodes VALUES (%s, %s, %s)",
                       (other_run, 1, 99.0))
            return db

        with patch("ax3l.interface.SnakeLab.DbMgr", side_effect=connect) as factory:
            self.assertEqual(SnakeLab().get_episode_losses(run_id),
                             [(1, None), (2, 0.5), (3, 0.0)])
        factory.assert_called_once_with(database="snakelab", initialize_event_tables=False)
        self.assertFalse(self.db._connection.open)

    def test_counts_all_statuses_and_repeated_configurations(self):
        count = self.query_count(("queued", "running", "completed", "failed", "cancelled"))
        self.assertEqual(count, 5)
        self.assertIsInstance(count, int)
        self.assertFalse(self.db._connection.open)

    def configuration_db(self):
        db = DbMgr(initialize_event_tables=False)
        self.addCleanup(db.close)
        db.execute("""CREATE TEMPORARY TABLE simulation_runs (
            id INT AUTO_INCREMENT PRIMARY KEY, run_id CHAR(36),
            status VARCHAR(16), high_score INT NULL)""")
        schema = (Path(__file__).resolve().parents[1] /
                  "pages/snake-lab/database-v3.sql").read_text()
        schema = schema[schema.index("CREATE TABLE"):schema.index(",\n\n    CONSTRAINT")]
        db.execute(schema.replace("CREATE TABLE IF NOT EXISTS", "CREATE TEMPORARY TABLE") + ")")
        additions = (Path(__file__).resolve().parents[1] / 'pages/snake-lab/database-v6.sql').read_text()
        db.execute(additions.split('ALTER TABLE simulation_episodes')[0])
        return db

    def insert_config(self, db, config, status="completed", score=3):
        run_id = str(uuid4())
        db.execute("INSERT INTO simulation_runs (run_id, status, high_score) VALUES (%s,%s,%s)",
                   (run_id, status, score))
        placeholders = ", ".join(["%s"] * (len(CONFIGURATION_FIELDS) + 1))
        db.execute(f"INSERT INTO configurations (run_id, {CONFIGURATION_COLUMNS}) VALUES ({placeholders})",
                   (run_id, *_config_values(config)))
        return run_id

    def test_available_parameters_restore_exhaustion_for_the_current_seed_and_draft_settings(self):
        from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb
        db = self.configuration_db()
        dal = SnakeLabDb(db)
        config = SimulationConfiguration.defaults()
        for layers, status in ((1, 'completed'), (2, 'failed'), (3, 'queued')):
            trial = deepcopy(config)
            trial['model']['layers'] = layers
            self.insert_config(db, trial, status)
        original = deepcopy(config)
        self.assertEqual(dal.available_parameters(config, ['layers', 'gamma', 'seed']), ['gamma', 'seed'])
        self.assertEqual(config, original)
        config['seed'] += 1
        self.assertEqual(dal.available_parameters(config, ['layers']), ['layers'])
        config['seed'] = original['seed']
        config['training']['batch_size'] = 32
        self.assertEqual(dal.available_parameters(config, ['layers']), ['layers'])
        # The draft is not stored, so only its changed alternatives exist in history.
        for layers in (2, 3):
            trial = deepcopy(config)
            trial['model']['layers'] = layers
            self.insert_config(db, trial)
        self.assertIsNone(dal.find_config_run(config))
        self.assertEqual(dal.available_parameters(config, ['layers']), [])

    def test_available_parameters_need_every_legal_reward_pair_and_ignore_invalid_history(self):
        from ax3l.app.snakelab.ParameterSpace import finite_choices
        from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb
        db = self.configuration_db()
        dal = SnakeLabDb(db)
        config = SimulationConfiguration.defaults()
        missing = (Fraction(1, 10), Fraction(-1, 10))
        for closer, further in finite_choices('reward_pair') - {missing}:
            trial = deepcopy(config)
            trial['game']['rewards'].update(closer_to_food=float(closer), further_from_food=float(further))
            self.insert_config(db, trial)
        trial['game']['rewards'].update(closer_to_food=6, further_from_food=0)
        self.insert_config(db, trial)
        self.assertEqual(dal.available_parameters(config, ['reward_pair']), ['reward_pair'])
        trial['game']['rewards'].update(closer_to_food=float(missing[0]), further_from_food=float(missing[1]))
        self.insert_config(db, trial, 'cancelled')
        self.assertEqual(dal.available_parameters(config, ['reward_pair']), [])

    def test_full_configuration_uniqueness_uses_values_and_all_statuses(self):
        from copy import deepcopy
        from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb
        db = self.configuration_db()
        dal = SnakeLabDb(db)
        candidate = SimulationConfiguration.defaults()
        self.assertTrue(dal.is_config_unique(candidate))
        for state in ('queued', 'running', 'completed', 'failed', 'cancelled'):
            with self.subTest(state=state):
                db.execute('DELETE FROM configurations')
                db.execute('DELETE FROM simulation_runs')
                run_id = self.insert_config(db, candidate, state)
                reordered = dict(reversed(list(candidate.items())))
                reordered['seed'] = float(candidate['seed'])
                self.assertFalse(dal.is_config_unique(reordered))
                self.assertEqual(dal.find_config_run(reordered), run_id)
                for _, path, _ in CONFIGURATION_FIELDS:
                    changed = deepcopy(candidate)
                    target = changed
                    for part in path[:-1]:
                        target = target[part]
                    target[path[-1]] = 'rnn' if isinstance(target[path[-1]], str) else target[path[-1]] + 1
                    self.assertTrue(dal.is_config_unique(changed), path)
                latest = self.insert_config(db, candidate, state)
                self.assertEqual(dal.find_config_run(candidate), latest)

    def test_comparison_reads_all_runs_in_numeric_learning_rate_order(self):
        from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb
        db = self.configuration_db()
        ids = []
        for lr, score, status in zip((.01, .002, .001), (12, 9, None), ('completed', 'completed', 'failed')):
            config = SimulationConfiguration.defaults()
            config['training']['learning_rate'] = lr
            ids.append(self.insert_config(db, config, status, score))
        dal = SnakeLabDb(db)
        history = dal.get_learning_rate_history()
        self.assertEqual([row['run_id'] for row in history], list(reversed(ids)))
        self.assertEqual([row['learning_rate'] for row in history], [.001, .002, .01])
        self.assertIsNone(history[0]['high_score'])
        self.assertEqual(dal.get_run_result(ids[0])['config']['training']['learning_rate'], .01)
        self.assertIsNone(dal.get_run_result(str(uuid4())))
        self.assertEqual(dal.get_config(ids[-1]), config)
        self.assertIsInstance(dal.get_config(ids[-1])['game']['rewards']['food'], float)
        self.assertIsNone(dal.get_config(str(uuid4())))

    def test_score_history_omits_seeds_and_preserves_sorted_repeated_scores(self):
        from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb
        db = self.configuration_db()
        config = SimulationConfiguration.defaults()
        for seed, score, state in ((9000, 12, 'completed'), (9001, 0, 'completed'),
                                   (9002, 12, 'completed'), (8999, None, 'completed'),
                                   (8998, 99, 'failed'), (9003, 3, 'completed')):
            config['seed'] = seed
            golden_id = self.insert_config(db, config, state, score)
        dal = SnakeLabDb(db)
        report = dal.get_learning_rate_report(golden_id)
        self.assertEqual(report, [{'learning_rate': config['training']['learning_rate'], 'results': [
            {'run_id': golden_id, 'status': 'completed', 'high_score': 3}], 'history': [0, 12, 12]}])
        self.assertEqual(dal.find_config_run(config), golden_id)
        self.assertIsNone(dal.find_config_run({**config, 'seed': 123}))

    def test_pair_reports_exclude_other_parameter_changes(self):
        from copy import deepcopy
        from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb
        db = self.configuration_db()
        config = SimulationConfiguration.defaults()
        golden_id = self.insert_config(db, config, score=4)
        changed = deepcopy(config)
        changed['seed'] += 1
        self.insert_config(db, changed, score=0)
        changed['training']['batch_size'] += 2
        self.insert_config(db, changed, score=99)
        dal = SnakeLabDb(db)
        self.assertEqual(dal.get_epsilon_report(golden_id), [
            {'initial': config['epsilon']['initial'], 'pairs': [
                {'decay': config['epsilon']['decay'], 'scores': [0, 4]}]}])
        rewards = dal.get_reward_report(golden_id)
        self.assertEqual(rewards['1']['-1'], [0, 4])
        self.assertEqual(sum(len(scores) for pairs in rewards.values() for scores in pairs.values()), 2)

    def test_nice_history_matches_the_complete_configuration(self):
        from copy import deepcopy
        from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb
        db = self.configuration_db()
        baseline = SimulationConfiguration.defaults()
        golden = self.insert_config(db, baseline, score=4)
        trial = deepcopy(baseline)
        trial['epsilon_nice'].update(probability=.01, steps=40)
        self.insert_config(db, trial, score=7)
        trial['seed'] += 1
        self.insert_config(db, trial, score=6)
        for section, key, value in (('model', 'type', 'rnn'), ('model', 'heads', 8),
                                    ('epsilon', 'decay', .99)):
            other = deepcopy(trial)
            other[section][key] = value
            self.insert_config(db, other, score=99)
        self.assertEqual(SnakeLabDb(db).get_epsilon_nice_report(golden), [
            {'probability': .005, 'pairs': [{'steps': 20, 'scores': [4]}, {'steps': 40, 'scores': []}]},
            {'probability': .01, 'pairs': [{'steps': 20, 'scores': []}, {'steps': 40, 'scores': [6, 7]}]},
        ])
        self.assertEqual(SnakeLabDb(db).get_config(golden), baseline)

    def test_episode_diagnostics_are_scoped_and_preserve_zero_counts(self):
        from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb
        db = DbMgr(initialize_event_tables=False)
        self.addCleanup(db.close)
        db.execute("""CREATE TEMPORARY TABLE simulation_episodes (
            run_id CHAR(36), epsilon DOUBLE, epsilon_injections INT,
            epsilon_nice_injections INT, reward DOUBLE, outcome VARCHAR(16))""")
        for row in (('run', .01, 4, 0, 1.5, 'wall'), ('run', 0, 0, 3, -.25, 'max_moves'),
                    ('other', 0, 100, 100, 100, 'snake')):
            db.execute('INSERT INTO simulation_episodes VALUES (%s,%s,%s,%s,%s,%s)', row)
        dal = SnakeLabDb(db)
        self.assertEqual(dal.get_episode_diagnostics('run'), dict(episodes=2, post_epsilon_episodes=1,
            epsilon_injections=4, epsilon_nice_injections=3, total_reward=1.25,
            wall=1, snake=0, max_moves=1, board_filled=0))
        empty = dal.get_episode_diagnostics('absent')
        self.assertEqual(empty['episodes'], 0)
        self.assertEqual(empty['epsilon_nice_injections'], 0)
        self.assertIsNone(empty['total_reward'])
