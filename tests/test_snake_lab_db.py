"""Run with AX3L_TEST_DEV_DB=1 and the disposable DEV DB_* credentials."""

import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from ax3l.app.DbMgr import DbMgr
from ax3l.interface.SnakeLab import SnakeLab


@unittest.skipUnless(os.environ.get("AX3L_TEST_DEV_DB") == "1", "requires DEV MariaDB")
class SnakeLabDbTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ["DB_NAME"], "ax3l_dev")
        credentials = {
            f"SNAKELAB_{key}": value
            for key, value in os.environ.items() if key.startswith("DB_")
        }
        env = patch.dict(os.environ, credentials)
        env.start()
        self.addCleanup(env.stop)
        initialization = patch.object(
            DbMgr, "_initialize_event_tables",
            side_effect=AssertionError("External connections must not initialize tables"),
        )
        initialization.start()
        self.addCleanup(initialization.stop)

    def query_count(self, statuses=()):
        def connect(**kwargs):
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
                       (run_id, project_version, config, config_hash, status)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (str(uuid4()), "test", "{}", "a" * 64, status),
                )
            return db

        with patch("ax3l.interface.SnakeLab.DbMgr", side_effect=connect) as factory:
            try:
                return SnakeLab().get_num_sims()
            finally:
                factory.assert_called_once_with(
                    env_prefix="SNAKELAB_DB", initialize_event_tables=False
                )

    def test_empty_database(self):
        self.assertEqual(self.query_count(), 0)
        self.assertFalse(self.db._connection.open)

    def test_episode_losses_are_scoped_ordered_and_preserve_nulls(self):
        run_id, other_run = str(uuid4()), str(uuid4())

        def connect(**kwargs):
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
        factory.assert_called_once_with(env_prefix="SNAKELAB_DB", initialize_event_tables=False)
        self.assertFalse(self.db._connection.open)

    def test_counts_all_statuses_and_repeated_configurations(self):
        count = self.query_count(("queued", "running", "completed", "failed", "cancelled"))
        self.assertEqual(count, 5)
        self.assertIsInstance(count, int)
        self.assertFalse(self.db._connection.open)

    def test_full_configuration_uniqueness_uses_json_values_and_all_statuses(self):
        import json
        from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb
        db = DbMgr(env_prefix='SNAKELAB_DB', initialize_event_tables=False)
        self.addCleanup(db.close)
        db.execute('CREATE TEMPORARY TABLE simulation_runs (config JSON NOT NULL, status VARCHAR(16))')
        dal = SnakeLabDb(db)
        candidate = {'seed': 1970, 'training': {'learning_rate': 0.003, 'batch_size': 24}}
        self.assertTrue(dal.is_config_unique(candidate))
        for state in ('queued', 'running', 'completed', 'failed', 'cancelled'):
            with self.subTest(state=state):
                db.execute('DELETE FROM simulation_runs')
                db.execute('INSERT INTO simulation_runs VALUES (%s, %s)', (json.dumps(candidate), state))
                reordered = {'training': {'batch_size': 24.0, 'learning_rate': 0.003}, 'seed': 1970.0}
                self.assertFalse(dal.is_config_unique(reordered))
                self.assertTrue(dal.is_config_unique({**candidate, 'seed': 1971}))
                self.assertTrue(dal.is_config_unique({'seed': 1970, 'training': {'learning_rate': 0.004, 'batch_size': 24}}))

    def test_comparison_reads_all_runs_in_numeric_learning_rate_order(self):
        import json
        from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb
        db = DbMgr(env_prefix='SNAKELAB_DB', initialize_event_tables=False)
        self.addCleanup(db.close)
        db.execute('''CREATE TEMPORARY TABLE simulation_runs (
            id INT AUTO_INCREMENT PRIMARY KEY, run_id CHAR(36), config JSON,
            status VARCHAR(16), high_score INT NULL)''')
        ids = [str(uuid4()) for _ in range(3)]
        for run_id, lr, score, status in zip(ids, (.01, .002, .001), (12, 9, None), ('completed', 'completed', 'failed')):
            db.execute('INSERT INTO simulation_runs (run_id, config, status, high_score) VALUES (%s,%s,%s,%s)',
                       (run_id, json.dumps({'training': {'learning_rate': lr}}), status, score))
        dal = SnakeLabDb(db)
        history = dal.get_learning_rate_history()
        self.assertEqual([row['run_id'] for row in history], list(reversed(ids)))
        self.assertEqual([row['learning_rate'] for row in history], [.001, .002, .01])
        self.assertIsNone(history[0]['high_score'])
        self.assertEqual(dal.get_run_result(ids[0])['config']['training']['learning_rate'], .01)
        self.assertIsNone(dal.get_run_result(str(uuid4())))

    def test_score_history_omits_seeds_and_preserves_sorted_repeated_scores(self):
        import json
        from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb
        db = DbMgr(env_prefix='SNAKELAB_DB', initialize_event_tables=False)
        self.addCleanup(db.close)
        db.execute('''CREATE TEMPORARY TABLE simulation_runs (
            id INT AUTO_INCREMENT PRIMARY KEY, run_id CHAR(36), config JSON,
            status VARCHAR(16), high_score INT NULL)''')
        golden_id = str(uuid4())
        config = {'seed': 9003, 'training': {'learning_rate': .002, 'batch_size': 24}}
        for seed, score, state in ((9000, 12, 'completed'), (9001, 0, 'completed'),
                                   (9002, 12, 'completed'), (8999, None, 'completed'),
                                   (8998, 99, 'failed'), (9003, 3, 'completed')):
            db.execute('INSERT INTO simulation_runs (run_id, config, status, high_score) VALUES (%s,%s,%s,%s)',
                       (golden_id if seed == 9003 else str(uuid4()), json.dumps({**config, 'seed': seed}), state, score))
        dal = SnakeLabDb(db)
        report = dal.get_learning_rate_report(golden_id)
        self.assertEqual(report, [{'learning_rate': .002, 'results': [
            {'run_id': golden_id, 'status': 'completed', 'high_score': 3}], 'history': [0, 12, 12]}])
        self.assertNotIn('seed', json.dumps(report))
        self.assertEqual(dal.find_config_run(config), golden_id)
        self.assertIsNone(dal.find_config_run({**config, 'seed': 123}))
