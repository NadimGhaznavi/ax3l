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
            "prompt_sent", "Conversation", "INFO", "Write a haiku.",
            process_id=self.process_id,
        )
        content = "A tree's quiet shade 🌳\nSecond line"
        reply_id = self.db.log(
            "reply_received", "Conversation", "INFO", content,
            process_id=self.process_id, parent_event_id=prompt_id,
        )
        self.assertGreater(reply_id, prompt_id)
        reader = DbMgr()
        try:
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

    def test_haiku_loop_records_linked_conversation(self):
        import io
        from pathlib import Path
        import runpy
        import tempfile
        from unittest.mock import Mock, patch

        run = runpy.run_path(str(Path(__file__).resolve().parents[1] / "ax3l/app/snakelab/main-loop.py"))["run"]
        body = b'{"choices":[{"message":{"content":"A haiku"}}],"usage":{"completion_tokens":20}}'
        llm = Mock(url="http://example/v1/chat/completions")
        llm.complete.return_value = (200, "Content-Type: application/json", body)
        with tempfile.TemporaryDirectory() as folder, patch("time.sleep") as sleep, patch("sys.stdout", new_callable=io.StringIO), patch.dict(run.__globals__, {"uuid4": lambda: self.process_id}):
            run(llm, Path(folder), self.db, count=2)
            sleep.assert_called_once_with(5)
        rows = self.db.query(
            """SELECT e.event_id, e.name, e.parent_event_id, m.content
               FROM events e JOIN event_messages m USING (event_id)
               WHERE process_id = %s ORDER BY event_id""",
            (self.process_id,),
        )
        self.assertEqual([row["name"] for row in rows], [
            "conversation_started", "prompt_sent", "reply_received",
            "wait_started", "wait_ended", "prompt_sent", "reply_received",
            "conversation_ended",
        ])
        self.assertEqual(rows[1]["content"], "Write a haiku.")
        self.assertEqual(rows[2]["content"], body.decode())
        self.assertEqual(rows[2]["parent_event_id"], rows[1]["event_id"])
        self.assertEqual(rows[6]["parent_event_id"], rows[5]["event_id"])
        self.assertEqual(rows[-1]["parent_event_id"], rows[0]["event_id"])

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
