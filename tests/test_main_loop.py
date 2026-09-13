import io
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import Mock, patch

from ax3l.constants.DAx3l import DAx3l


MAIN = runpy.run_path(str(Path(__file__).resolve().parents[1] / "ax3l/app/snakelab/main-loop.py"))["main"]


class MainLoopTests(unittest.TestCase):
    def test_raw_log_switch_controls_all_capture_files(self):
        main = MAIN
        for enabled in (False, True):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as folder:
                output = Path(folder) / "snakelab"
                db = Mock()
                llm = Mock(url="http://example/v1/chat/completions")
                optimize = Mock()
                with patch.object(DAx3l, "RAW_LOGS_ENABLED", enabled), patch.dict(main.__globals__, {"DbMgr": lambda: db, "LLM": lambda url: llm, "run_optimization": optimize}), patch("ax3l.interface.SnakeLab.SnakeLab.get_num_sims", return_value=1), patch("sys.stdout", new_callable=io.StringIO):
                    self.assertEqual(main(["--url", "http://example", "--output", str(output)]), 0)
                optimize.assert_called_once()
                self.assertIs(optimize.call_args.args[0], llm)
                self.assertIs(optimize.call_args.args[2], db)
                db.close.assert_called_once()
                if enabled:
                    files = {path.name for path in output.glob("*/*")}
                    self.assertEqual(files, {"run.log"})
                else:
                    self.assertFalse(output.exists())
