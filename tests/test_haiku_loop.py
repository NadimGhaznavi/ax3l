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


RUN = runpy.run_path(str(Path(__file__).resolve().parents[1] / "ax3l/app/snakelab/main-loop.py"))["run"]


class HaikuLoopTests(unittest.TestCase):
    def test_prompt_formats(self):
        prompt = GenerateHaiku()
        self.assertEqual(json.loads(prompt.to_json()), {
            "role": "user", "content": prompt.to_md(),
        })

    def test_two_turns_capture_unparsed_output_and_wait(self):
        body = b'{"choices":[],"reasoning":"unfiltered","unknown":true}\n'
        llm = Mock(url="http://example/v1/chat/completions")
        llm.complete.return_value = (200, "Content-Type: application/json\n", body)
        with tempfile.TemporaryDirectory() as folder, patch("time.sleep") as sleep, patch("sys.stdout", new_callable=io.StringIO):
            output = Path(folder)
            RUN(llm, output, count=2)
            sleep.assert_called_once_with(5)
            self.assertEqual(llm.complete.call_count, 2)
            for turn in (1, 2):
                self.assertEqual((output / f"{turn:04d}.response.body").read_bytes(), body)
                request = json.loads((output / f"{turn:04d}.request.json").read_bytes())
                self.assertEqual(request, {
                    "messages": [{"role": "user", "content": "Write a haiku."}],
                    "stream": False,
                })

    def test_http_error_body_is_captured_before_stopping(self):
        error = HTTPError("http://example", 503, "Unavailable", {}, io.BytesIO(b"model unavailable"))
        with tempfile.TemporaryDirectory() as folder, patch("ax3l.interface.LLM.urlopen", side_effect=error), patch("time.sleep") as sleep, patch("sys.stdout", new_callable=io.StringIO):
            output = Path(folder)
            with self.assertRaisesRegex(RuntimeError, "HTTP 503"):
                RUN(LLM("http://example"), output, count=2)
            self.assertEqual((output / "0001.response.body").read_bytes(), b"model unavailable")
            sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
