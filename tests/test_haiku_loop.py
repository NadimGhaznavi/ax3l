import io
import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from ax3l.app.snakelab.prompts.GenerateHaiku import GenerateHaiku
from ax3l.interface.LLM import LLM
from ax3l.constants.DAx3l import DAx3l


RUN = runpy.run_path(str(Path(__file__).resolve().parents[1] / "ax3l/app/snakelab/main-loop.py"))["run"]


class HaikuLoopTests(unittest.TestCase):
    def test_raw_log_switch_controls_all_capture_files(self):
        main = RUN.__globals__["main"]
        for enabled in (False, True):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as folder:
                output = Path(folder) / "haiku"
                db = Mock()
                llm = Mock(url="http://example/v1/chat/completions")
                llm.complete.return_value = (200, "Content-Type: application/json", b'{"choices":[]}')
                with patch.object(DAx3l, "RAW_LOGS_ENABLED", enabled), patch.dict(main.__globals__, {"DbMgr": lambda: db, "LLM": lambda url: llm}), patch("ax3l.interface.SnakeLab.SnakeLab.get_num_sims", return_value=1), patch("sys.stdout", new_callable=io.StringIO):
                    self.assertEqual(main(["--url", "http://example", "--output", str(output), "--count", "1"]), 0)
                self.assertEqual([call.args[0] for call in db.log.call_args_list], [
                    "conversation_started", "prompt_sent", "reply_received", "conversation_ended",
                ])
                db.close.assert_called_once()
                if enabled:
                    files = {path.name for path in output.glob("*/*")}
                    self.assertEqual(files, {"run.log", "0001.request.json", "0001.response.body", "0001.response.headers"})
                else:
                    self.assertFalse(output.exists())

    def test_prompt_formats(self):
        prompt = GenerateHaiku(17)
        self.assertEqual(prompt.to_md(), "Write a haiku based on the number 17.")
        self.assertEqual(json.loads(prompt.to_json()), {
            "role": "user", "content": prompt.to_md(),
        })

    @patch.object(DAx3l, "RAW_LOGS_ENABLED", True)
    @patch("random.randint", side_effect=[0, 30])
    def test_two_turns_capture_unparsed_output_and_wait(self, randint):
        body = b'{"choices":[],"reasoning":"unfiltered","unknown":true}\n'
        llm = Mock(url="http://example/v1/chat/completions")
        llm.complete.return_value = (200, "Content-Type: application/json\n", body)
        with tempfile.TemporaryDirectory() as folder, patch("time.sleep") as sleep, patch("sys.stdout", new_callable=io.StringIO):
            output = Path(folder)
            RUN(llm, output, Mock(), count=2)
            sleep.assert_called_once_with(5)
            self.assertEqual(llm.complete.call_count, 2)
            for turn in (1, 2):
                self.assertEqual((output / f"{turn:04d}.response.body").read_bytes(), body)
                request = json.loads((output / f"{turn:04d}.request.json").read_bytes())
                self.assertEqual(request, {
                    "messages": [{"role": "user", "content": f"Write a haiku based on the number {0 if turn == 1 else 30}."}],
                    "stream": False,
                })
            self.assertEqual(randint.call_count, 2)
            randint.assert_called_with(0, 30)

    @patch.object(DAx3l, "RAW_LOGS_ENABLED", True)
    def test_http_error_body_is_captured_before_stopping(self):
        error = HTTPError("http://example", 503, "Unavailable", {}, io.BytesIO(b"model unavailable"))
        db = Mock()
        with tempfile.TemporaryDirectory() as folder, patch("ax3l.interface.LLM.urlopen", side_effect=error), patch("time.sleep") as sleep, patch("sys.stdout", new_callable=io.StringIO):
            output = Path(folder)
            with self.assertRaisesRegex(RuntimeError, "HTTP 503"):
                RUN(LLM("http://example"), output, db, count=2)
            self.assertEqual((output / "0001.response.body").read_bytes(), b"model unavailable")
            sleep.assert_not_called()
        self.assertEqual([call.args[0] for call in db.log.call_args_list], [
            "conversation_started", "prompt_sent", "llm_request_failed", "conversation_ended",
        ])
        self.assertEqual(db.log.call_args.args[2], "ERROR")

    def test_interrupt_during_wait_ends_conversation(self):
        llm = Mock(url="http://example/v1/chat/completions")
        llm.complete.return_value = (200, "", b"{}")
        db = Mock()
        with tempfile.TemporaryDirectory() as folder, patch("time.sleep", side_effect=KeyboardInterrupt), patch("sys.stdout", new_callable=io.StringIO):
            with self.assertRaises(KeyboardInterrupt):
                RUN(llm, Path(folder), db, count=2)
        self.assertEqual([call.args[0] for call in db.log.call_args_list], [
            "conversation_started", "prompt_sent", "reply_received", "wait_started", "conversation_ended",
        ])
        self.assertEqual(db.log.call_args.args[3], "Stopped by user.")


if __name__ == "__main__":
    unittest.main()
