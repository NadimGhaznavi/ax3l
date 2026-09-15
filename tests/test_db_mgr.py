"""Integration checks against the disposable ax3l_dev MariaDB database.

Load its DB_* environment variables and set AX3L_TEST_DEV_DB=1 to run.
"""

import os
import unittest
from uuid import uuid4


@unittest.skipUnless(os.environ.get("AX3L_TEST_DEV_DB") == "1", "requires DEV MariaDB")
class DbMgrTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ["DB_NAME"], "ax3l_dev")
        from ax3l.app.DbMgr import DbMgr

        self.db = DbMgr()
        self.process_id = str(uuid4())
        self.addCleanup(self.db.close)
        self.addCleanup(
            self.db.execute,
            "DELETE FROM events WHERE process_id = %s ORDER BY event_id DESC",
            (self.process_id,),
        )

    def event(self):
        self.db.execute(
            "INSERT INTO events (name, category, log_level, process_id) VALUES (%s, %s, %s, %s)",
            ("reply_received", "Conversation", "INFO", self.process_id),
        )
        return self.db.query("SELECT LAST_INSERT_ID() AS event_id")[0]["event_id"]

    def test_current_golden_config_selects_latest_creation(self):
        from ax3l.app.EventLogDb import EventLogDb

        with self.db.transaction():
            for category, reason in (("Configuration", "Initial defaults"),
                                     ("Configuration", "Parameter x: 2 > 4"),
                                     ("Other", "Not a golden configuration")):
                self.db.execute(
                    "INSERT INTO events (name, category, log_level, process_id) VALUES (%s, %s, %s, %s)",
                    ("golden_config_created", category, "INFO", self.process_id),
                )
                event_id = self.db.query("SELECT LAST_INSERT_ID() AS event_id")[0]["event_id"]
                self.db.execute("INSERT INTO event_messages VALUES (%s, %s)", (event_id, reason))
            self.assertEqual(EventLogDb(self.db).current_golden_config(), {
                "process_id": self.process_id, "reason": "Parameter x: 2 > 4",
            })
            self.db.execute("DELETE FROM events WHERE process_id = %s", (self.process_id,))

    def test_round_trip_and_reinitialization(self):
        from ax3l.app.DbMgr import DbMgr

        content = "A tree's quiet shade 🌳\nSecond line"
        with self.db.transaction():
            event_id = self.event()
            self.db.execute("INSERT INTO event_messages VALUES (%s, %s)", (event_id, content))
            for key, value in (("model", "Qwen2.5-VL"), ("prompt_tokens", "24")):
                self.db.execute("INSERT INTO event_key_values VALUES (%s, %s, %s)", (event_id, key, value))
            for position, value in ((1, "second"), (0, "first")):
                self.db.execute("INSERT INTO event_list_items VALUES (%s, %s, %s)", (event_id, position, value))
        reader = DbMgr()
        try:
            self.assertEqual(reader.query("SELECT content FROM event_messages WHERE event_id = %s", (event_id,)), [{"content": content}])
            self.assertEqual(reader.query("SELECT value FROM event_list_items WHERE event_id = %s ORDER BY position", (event_id,)), [{"value": "first"}, {"value": "second"}])
            self.assertEqual(reader.query("SELECT value FROM event_key_values WHERE event_id = %s AND entry_key = %s", (event_id, "prompt_tokens")), [{"value": "24"}])
        finally:
            reader.close()
        self.db.execute("DELETE FROM events WHERE event_id = %s", (event_id,))
        for table in ("event_messages", "event_list_items", "event_key_values"):
            self.assertEqual(self.db.query(f"SELECT * FROM {table} WHERE event_id = %s", (event_id,)), [])

    def test_log_commits_content_and_links(self):
        from ax3l.app.DbMgr import DbMgr

        prompt_id = self.db.log(
            "prompt_sent", "Conversation", "INFO", "Describe the configuration.",
            process_id=self.process_id, source_name="GoldenConfig", parameter="reward_pair",
        )
        content = "A tree's quiet shade 🌳\nSecond line"
        reply_id = self.db.log(
            "reply_received", "Conversation", "INFO", content,
            process_id=self.process_id, parent_event_id=prompt_id,
        )
        self.assertGreater(reply_id, prompt_id)
        reader = DbMgr()
        try:
            from ax3l.app.EventLogDb import EventLogDb
            self.assertEqual(EventLogDb(reader).get(prompt_id)['source_name'], 'GoldenConfig')
            self.assertIsNone(EventLogDb(reader).get(reply_id)['source_name'])
            self.assertEqual(EventLogDb(reader).get(prompt_id)['parameter'], 'reward_pair')
            self.assertIsNone(EventLogDb(reader).get(reply_id)['parameter'])
            recent = {row['event_id']: row for row in EventLogDb(reader).recent()}
            self.assertEqual(recent[prompt_id]['parameter'], 'reward_pair')
            rows = reader.query(
                """SELECT e.name, e.category, e.log_level, e.process_id,
                          e.parent_event_id, m.content
                   FROM events e JOIN event_messages m USING (event_id)
                   WHERE e.event_id = %s""",
                (reply_id,),
            )
            self.assertEqual(rows, [{
                "name": "reply_received", "category": "Conversation",
                "log_level": "INFO", "process_id": self.process_id,
                "parent_event_id": prompt_id, "content": content,
            }])
        finally:
            reader.close()

    def test_log_failure_leaves_no_envelope(self):
        import pymysql

        # Force rejection of the message insert after the envelope was inserted.
        with self.assertRaises(pymysql.IntegrityError):
            self.db.log(
                "reply_received", "Conversation", "INFO", None,
                process_id=self.process_id,
            )
        self.assertEqual(
            self.db.query("SELECT * FROM events WHERE process_id = %s", (self.process_id,)),
            [],
        )

    def test_duplicate_dictionary_key_rolls_back_whole_event(self):
        import pymysql

        with self.assertRaises(pymysql.IntegrityError):
            with self.db.transaction():
                event_id = self.event()
                self.db.execute("INSERT INTO event_key_values VALUES (%s, %s, %s)", (event_id, "model", "Qwen"))
                self.db.execute("INSERT INTO event_key_values VALUES (%s, %s, %s)", (event_id, "model", "duplicate"))
        self.assertEqual(self.db.query("SELECT * FROM events WHERE process_id = %s", (self.process_id,)), [])

    def test_latest_proposal_recovers_pending_run_and_comparison(self):
        import json
        from ax3l.app.EventLogDb import EventLogDb
        self.db.log('proposal_accepted', 'Configuration', 'INFO', 'learning_rate: .003', process_id=self.process_id)
        dal = EventLogDb(self.db)
        self.assertEqual(dal.latest_snakelab_proposal(), {
            'process_id': self.process_id, 'comparison_id': None, 'comparison': None})
        snapshot = json.dumps({'golden_run_id': 'gold', 'latest_run_id': self.process_id,
                               'current_golden_run_id': self.process_id, 'reason': 'High score: 11 > 10'})
        event_id = self.db.log('configuration_compared', 'Configuration', 'INFO', snapshot, process_id=self.process_id)
        self.db.log('proposal_accepted', 'Other', 'INFO', 'unrelated', process_id=self.process_id)
        self.assertEqual(dal.latest_snakelab_proposal(), {
            'process_id': self.process_id, 'comparison_id': event_id, 'comparison': snapshot})

    def test_stagnation_reset_and_rotation_recovery_queries(self):
        import json
        from ax3l.app.EventLogDb import EventLogDb
        dal = EventLogDb(self.db)
        def log(name, content='test', parent=None):
            return self.db.log(name, 'Configuration', 'INFO', content,
                               process_id=self.process_id, parent_event_id=parent)
        log('golden_config_created')
        self.assertEqual(dal.stagnant_rounds(), 0)
        log('configuration_compared')
        log('configuration_compared')
        self.assertEqual(dal.stagnant_rounds(), 0)  # Uncheckpointed comparisons are not full cycles.
        log('golden_config_created')
        self.assertEqual(dal.stagnant_rounds(), 0)
        log('proposal_accepted')
        intent = log('seed_rotation_started', json.dumps({'config': {'seed': 2}}))
        self.assertEqual(dal.pending_seed_rotation()['event_id'], intent)
        submitted = log('golden_config_seed_incremented', parent=intent)
        self.assertEqual(dal.pending_seed_rotation()['run_id'], self.process_id)
        self.assertIsNone(dal.latest_snakelab_proposal())
        log('golden_config_created', parent=submitted)
        self.assertIsNone(dal.pending_seed_rotation())
        self.assertEqual(dal.latest_seed_baseline(), self.process_id)


if __name__ == "__main__":
    unittest.main()
