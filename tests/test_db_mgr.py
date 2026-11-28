"""Integration checks against the disposable ax3l_test MariaDB database.

Load its DB_* environment variables and set AX3L_TEST_DB=1 to run.
"""

import os
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from ax3l.interface.database.EventLogDb import EventLogDb


class DatabaseLifecycleTests(unittest.TestCase):
    def test_initialization_failure_closes_the_connection(self):
        from ax3l.interface.database.DbMgr import DbMgr

        with patch.dict(os.environ, DB_HOST='test-host', DB_NAME='ax3l_test',
                        DB_USER='test-user', DB_PASSWORD='test-password'), \
                patch('ax3l.interface.database.DbMgr.pymysql.connect') as connect, \
                patch('ax3l.interface.database.DbMgr.EventSchema') as schema:
            schema.return_value.initialize.side_effect = RuntimeError('Schema unavailable')
            with self.assertRaisesRegex(RuntimeError, 'Schema unavailable'):
                DbMgr()
            schema.return_value.initialize.assert_called_once_with()
            connect.return_value.close.assert_called_once_with()

    def test_external_connection_has_no_schema_side_effect(self):
        from ax3l.interface.database.DbMgr import DbMgr

        with patch.dict(os.environ, DB_HOST='test-host', DB_NAME='ax3l_test',
                        DB_USER='test-user', DB_PASSWORD='test-password'), \
                patch('ax3l.interface.database.DbMgr.pymysql.connect') as connect, \
                patch('ax3l.interface.database.DbMgr.EventSchema') as schema:
            db = DbMgr(database='snakelab', initialize_event_tables=False)
            schema.assert_not_called()
            self.assertEqual(connect.call_args.kwargs['database'], 'snakelab')
            db.close()
            connect.return_value.close.assert_called_once_with()


class EventVersionTests(unittest.TestCase):
    def test_version_is_written_with_submission_and_message_in_one_transaction(self):
        from ax3l.interface.database.DbMgr import DbMgr

        db = object.__new__(DbMgr)
        db._connection = Mock()
        db.execute = Mock()
        db.query = Mock(return_value=[{'event_id': 4}])
        for version in ('1.0.7', None):
            with self.subTest(version=version):
                db.execute.reset_mock()
                db._connection.reset_mock()
                self.assertEqual(EventLogDb(db).log('simulation_submitted', 'SnakeLab', 'INFO',
                                        'Submitted config.', process_id='run',
                                        ax3l_version=version), 4)
                sql, values = db.execute.call_args_list[0].args
                self.assertIn('ax3l_version', sql)
                self.assertEqual(values, ('simulation_submitted', 'SnakeLab', 'INFO',
                                          'run', None, None, None, version))
                db._connection.commit.assert_called_once()
        db._connection.reset_mock()
        db.execute.side_effect = [1, RuntimeError('message write failed')]
        with self.assertRaises(RuntimeError):
            EventLogDb(db).log('simulation_submitted', 'SnakeLab', 'INFO', 'Submitted config.',
                   ax3l_version='1.0.7')
        db._connection.commit.assert_not_called()
        db._connection.rollback.assert_called_once()


@unittest.skipUnless(os.environ.get("AX3L_TEST_DB") == "1", "requires disposable MariaDB test database")
class DbMgrTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ["DB_NAME"], "ax3l_test")
        from ax3l.interface.database.DbMgr import DbMgr

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
        from ax3l.interface.database.DbMgr import DbMgr

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
        from ax3l.interface.database.DbMgr import DbMgr

        prompt_id = EventLogDb(self.db).log(
            "prompt_sent", "Conversation", "INFO", "Describe the configuration.",
            process_id=self.process_id, source_name="GoldenConfig", parameter="reward_pair",
            ax3l_version="1.0.7",
        )
        content = "A tree's quiet shade 🌳\nSecond line"
        reply_id = EventLogDb(self.db).log(
            "reply_received", "Conversation", "INFO", content,
            process_id=self.process_id, parent_event_id=prompt_id,
        )
        self.assertGreater(reply_id, prompt_id)
        reader = DbMgr()
        try:
            self.assertEqual(EventLogDb(reader).get(prompt_id)['source_name'], 'GoldenConfig')
            self.assertIsNone(EventLogDb(reader).get(reply_id)['source_name'])
            self.assertEqual(EventLogDb(reader).get(prompt_id)['parameter'], 'reward_pair')
            self.assertEqual(EventLogDb(reader).get(prompt_id)['ax3l_version'], '1.0.7')
            self.assertIsNone(EventLogDb(reader).get(reply_id)['ax3l_version'])
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
            EventLogDb(self.db).log(
                "reply_received", "Conversation", "INFO", None,
                process_id=self.process_id,
            )
        self.assertEqual(
            self.db.query("SELECT * FROM events WHERE process_id = %s", (self.process_id,)),
            [],
        )

    def test_live_capture_is_committed_before_request_completion_and_survives_reconnection(self):
        import json
        from ax3l.interface.database.DbMgr import DbMgr
        from ax3l.interface.LLMResponseCapture import LLMResponseCapture

        response = dict(choices=[dict(message=dict(reasoning_content="Inspect 🌳 while waiting."))])
        with LLMResponseCapture(EventLogDb(self.db), 12, process_id=self.process_id,
                                parent_event_id=self.event(), source_name='selection', parameter='training') as capture:
            capture.receive(response)
            reader = DbMgr(initialize_event_tables=False)
            try:
                rows = reader.query('''SELECT e.event_id, m.content FROM events e
                    JOIN event_messages m USING (event_id)
                    WHERE e.process_id=%s AND e.name='llm_response_captured' ''', (self.process_id,))
                self.assertEqual(len(rows), 1)
                event_id = rows[0]['event_id']
                saved = json.loads(rows[0]['content'])
                self.assertEqual(saved['choices'], response['choices'])
                self.assertEqual(saved['capture']['status'], 'in_progress')
            finally:
                reader.close()
        reader = DbMgr(initialize_event_tables=False)
        try:
            self.assertEqual(json.loads(EventLogDb(reader).get(event_id)['content'])['capture']['status'], 'completed')
        finally:
            reader.close()

    def test_duplicate_dictionary_key_rolls_back_whole_event(self):
        import pymysql

        with self.assertRaises(pymysql.IntegrityError):
            with self.db.transaction():
                event_id = self.event()
                self.db.execute("INSERT INTO event_key_values VALUES (%s, %s, %s)", (event_id, "model", "Qwen"))
                self.db.execute("INSERT INTO event_key_values VALUES (%s, %s, %s)", (event_id, "model", "duplicate"))
        self.assertEqual(self.db.query("SELECT * FROM events WHERE process_id = %s", (self.process_id,)), [])


if __name__ == "__main__":
    unittest.main()
