"""Run with AX3L_TEST_DEV_DB=1 and the disposable DEV DB_* credentials."""

import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from ax3l.app.DbMgr import DbMgr
from ax3l.interface.SnakeLab import SnakeLab
from ax3l.app.snakelab.GenerateDefaultConfig import GenerateDefaultConfig
from ax3l.app.snakelab.SnakeLabDb import CONFIGURATION_COLUMNS, CONFIGURATION_FIELDS, _config_values


@unittest.skipUnless(os.environ.get("AX3L_TEST_DEV_DB") == "1", "requires DEV MariaDB")
class SnakeLabDbTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ["DB_NAME"], "ax3l_dev")
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
        return db

    def insert_config(self, db, config, status="completed", score=3):
        run_id = str(uuid4())
        db.execute("INSERT INTO simulation_runs (run_id, status, high_score) VALUES (%s,%s,%s)",
                   (run_id, status, score))
        placeholders = ", ".join(["%s"] * (len(CONFIGURATION_FIELDS) + 1))
        db.execute(f"INSERT INTO configurations (run_id, {CONFIGURATION_COLUMNS}) VALUES ({placeholders})",
                   (run_id, *_config_values(config)))
        return run_id

    def test_full_configuration_uniqueness_uses_values_and_all_statuses(self):
        from copy import deepcopy
        from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb
        db = self.configuration_db()
        dal = SnakeLabDb(db)
        candidate = GenerateDefaultConfig().run()
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
                    target[path[-1]] += 1
                    self.assertTrue(dal.is_config_unique(changed), path)
                latest = self.insert_config(db, candidate, state)
                self.assertEqual(dal.find_config_run(candidate), latest)

    def test_comparison_reads_all_runs_in_numeric_learning_rate_order(self):
        from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb
        db = self.configuration_db()
        ids = []
        for lr, score, status in zip((.01, .002, .001), (12, 9, None), ('completed', 'completed', 'failed')):
            config = GenerateDefaultConfig().run()
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
        self.assertIsInstance(dal.get_config(ids[-1])['game']['rewards']['food'], int)
        self.assertIsNone(dal.get_config(str(uuid4())))

    def test_score_history_omits_seeds_and_preserves_sorted_repeated_scores(self):
        from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb
        db = self.configuration_db()
        config = GenerateDefaultConfig().run()
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
        config = GenerateDefaultConfig().run()
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
        self.assertEqual(rewards['2']['-2'], [0, 4])
        self.assertEqual(sum(len(scores) for pairs in rewards.values() for scores in pairs.values()), 2)
