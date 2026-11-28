"""Run with AX3L_TEST_DB=1 and the disposable test DB_* credentials."""

import os
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from ax3l.interface.database.DbMgr import DbMgr
from ax3l.interface.SnakeLab import SnakeLab
from ax3l.interface.SimulationConfiguration import SimulationConfiguration
from ax3l.interface.database.SnakeLabDb import CONFIGURATION_COLUMNS, CONFIGURATION_FIELDS, _config_values


@unittest.skipUnless(os.environ.get("AX3L_TEST_DB") == "1", "requires disposable MariaDB test database")
class SnakeLabDbTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ["DB_NAME"], "ax3l_test")
        initialization = patch(
            "ax3l.interface.database.EventSchema.EventSchema.initialize",
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

    def test_episode_scores_are_scoped_to_the_run_and_ordered_through_the_interface(self):
        db = DbMgr(initialize_event_tables=False)
        self.addCleanup(lambda: db.close() if db._connection.open else None)
        db.execute('''CREATE TEMPORARY TABLE simulation_episodes (
            run_id CHAR(36), episode INT, score INT
        )''')
        run_id, other_run = str(uuid4()), str(uuid4())
        for row in ((run_id, 3, 8), (other_run, 1, 99), (run_id, 1, 0), (run_id, 2, 4)):
            db.execute('INSERT INTO simulation_episodes VALUES (%s, %s, %s)', row)
        with patch('ax3l.interface.SnakeLab.DbMgr', return_value=db) as factory:
            self.assertEqual(SnakeLab().get_episode_scores(run_id), [
                dict(episode=1, score=0), dict(episode=2, score=4), dict(episode=3, score=8),
            ])
        factory.assert_called_once_with(database='snakelab', initialize_event_tables=False)
        self.assertFalse(db._connection.open)

    def test_exploration_episodes_are_scoped_ordered_and_closed_through_the_interface(self):
        db = DbMgr(initialize_event_tables=False)
        self.addCleanup(lambda: db.close() if db._connection.open else None)
        db.execute('''CREATE TEMPORARY TABLE simulation_episodes (
            run_id CHAR(36), episode INT, score INT, epsilon DOUBLE, steps INT,
            epsilon_nice_injections INT
        )''')
        run_id, other = str(uuid4()), str(uuid4())
        for row in ((run_id, 3, 8, 0, 100, 20), (other, 1, 99, 0, 200, 100),
                    (run_id, 4, 2, None, 40, 6),
                    (run_id, 1, 0, .9, 10, 0), (run_id, 2, 4, .4, 50, 0)):
            db.execute('INSERT INTO simulation_episodes VALUES (%s, %s, %s, %s, %s, %s)', row)
        with patch('ax3l.interface.SnakeLab.DbMgr', return_value=db) as factory:
            self.assertEqual(SnakeLab().get_exploration_episodes(run_id), [
                dict(episode=1, score=0, epsilon=.9),
                dict(episode=2, score=4, epsilon=.4),
                dict(episode=3, score=8, epsilon=0),
                dict(episode=4, score=2, epsilon=None),
            ])
        factory.assert_called_once_with(database='snakelab', initialize_event_tables=False)
        self.assertFalse(db._connection.open)

    def test_reward_episodes_are_scoped_ordered_and_preserve_missing_outcomes(self):
        db = DbMgr(initialize_event_tables=False)
        self.addCleanup(lambda: db.close() if db._connection.open else None)
        db.execute('''CREATE TEMPORARY TABLE simulation_episodes (
            run_id CHAR(36), episode INT, score INT, steps INT, outcome VARCHAR(16)
        )''')
        run_id, other = str(uuid4()), str(uuid4())
        for row in ((run_id, 3, 8, 100, None), (other, 1, 99, 200, 'wall'),
                    (run_id, 1, 0, 10, 'wall'), (run_id, 2, 4, 50, 'snake')):
            db.execute('INSERT INTO simulation_episodes VALUES (%s, %s, %s, %s, %s)', row)
        with patch('ax3l.interface.SnakeLab.DbMgr', return_value=db) as factory:
            self.assertEqual(SnakeLab().get_reward_episodes(run_id), [
                dict(episode=1, score=0, steps=10, outcome='wall'),
                dict(episode=2, score=4, steps=50, outcome='snake'),
                dict(episode=3, score=8, steps=100, outcome=None),
            ])
        factory.assert_called_once_with(database='snakelab', initialize_event_tables=False)
        self.assertFalse(db._connection.open)

    def test_training_episodes_are_scoped_ordered_and_preserve_missing_and_zero_losses(self):
        db = DbMgr(initialize_event_tables=False)
        self.addCleanup(lambda: db.close() if db._connection.open else None)
        db.execute('''CREATE TEMPORARY TABLE simulation_episodes (
            run_id CHAR(36), episode INT, score INT, loss DOUBLE
        )''')
        run_id, other = str(uuid4()), str(uuid4())
        for row in ((run_id, 3, 8, .4), (other, 1, 99, 99), (run_id, 1, 0, None), (run_id, 2, 4, 0)):
            db.execute('INSERT INTO simulation_episodes VALUES (%s, %s, %s, %s)', row)
        with patch('ax3l.interface.SnakeLab.DbMgr', return_value=db) as factory:
            self.assertEqual(SnakeLab().get_training_episodes(run_id), [
                dict(episode=1, score=0, loss=None), dict(episode=2, score=4, loss=0),
                dict(episode=3, score=8, loss=.4),
            ])
        factory.assert_called_once_with(database='snakelab', initialize_event_tables=False)
        self.assertFalse(db._connection.open)

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



    def test_configuration_lookup_uses_all_values_statuses_and_latest_matching_run(self):
        from copy import deepcopy
        from ax3l.interface.database.SnakeLabDb import SnakeLabDb
        db = self.configuration_db()
        dal = SnakeLabDb(db)
        candidate = SimulationConfiguration.defaults()
        self.assertIsNone(dal.find_config_run(candidate))
        for state in ('queued', 'running', 'completed', 'failed', 'cancelled'):
            with self.subTest(state=state):
                db.execute('DELETE FROM configurations')
                db.execute('DELETE FROM simulation_runs')
                run_id = self.insert_config(db, candidate, state)
                reordered = dict(reversed(list(candidate.items())))
                reordered['seed'] = float(candidate['seed'])
                self.assertIsNotNone(dal.find_config_run(reordered))
                self.assertEqual(dal.find_config_run(reordered), run_id)
                for _, path, _ in CONFIGURATION_FIELDS:
                    changed = deepcopy(candidate)
                    target = changed
                    for part in path[:-1]:
                        target = target[part]
                    target[path[-1]] = 'rnn' if isinstance(target[path[-1]], str) else target[path[-1]] + 1
                    self.assertIsNone(dal.find_config_run(changed), path)
                latest = self.insert_config(db, candidate, state)
                self.assertEqual(dal.find_config_run(candidate), latest)

    def test_configuration_and_result_reads_preserve_values(self):
        from ax3l.interface.database.SnakeLabDb import SnakeLabDb
        db = self.configuration_db()
        ids = []
        for lr, score, status in zip((.01, .002, .001), (12, 9, None), ('completed', 'completed', 'failed')):
            config = SimulationConfiguration.defaults()
            config['training']['learning_rate'] = lr
            ids.append(self.insert_config(db, config, status, score))
        dal = SnakeLabDb(db)
        self.assertEqual(dal.get_run_result(ids[0])['config']['training']['learning_rate'], .01)
        self.assertIsNone(dal.get_run_result(str(uuid4())))
        self.assertEqual(dal.get_config(ids[-1]), config)
        self.assertIsInstance(dal.get_config(ids[-1])['game']['rewards']['food'], float)
        self.assertIsNone(dal.get_config(str(uuid4())))




    def test_episode_diagnostics_are_scoped_and_preserve_zero_counts(self):
        from ax3l.interface.database.SnakeLabDb import SnakeLabDb
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
