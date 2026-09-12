import io
import json
from pathlib import Path
import runpy
import unittest
from unittest.mock import Mock, patch

from jsonschema import Draft202012Validator

from ax3l.app.snakelab.GenerateDefaultConfig import GenerateDefaultConfig


ROOT = Path(__file__).resolve().parents[1]


class DefaultConfigTests(unittest.TestCase):
    def test_defaults_form_a_valid_complete_configuration(self):
        schema = json.loads((ROOT / "ax3l/app/snakelab/simulation-config-v2.schema.json").read_text())
        config = GenerateDefaultConfig().run()
        Draft202012Validator(schema).validate(config)
        self.assertEqual(config["training"]["batch_size"], 24)
        self.assertEqual(config["game"]["rewards"]["wall"], -10)
        config["training"]["batch_size"] = 8
        self.assertEqual(GenerateDefaultConfig().run()["training"]["batch_size"], 24)

    def test_startup_generates_only_for_an_empty_database(self):
        for num_sims in (0, 3):
            with self.subTest(num_sims=num_sims):
                main = runpy.run_path(str(ROOT / "ax3l/app/snakelab/main-loop.py"))["main"]
                db = Mock()
                snake = Mock()
                snake.get_num_sims.return_value = num_sims
                snake.submit_simulation.return_value = "f6e72cb3-9bcf-4669-b368-a17c656bad79"
                snake.get_simulation_status.side_effect = ["queued", "running", "running", "completed"]
                run = Mock()
                with patch.dict(main.__globals__, {
                    "DbMgr": lambda: db, "SnakeLab": lambda: snake, "run_first_iteration": run,
                }), patch("time.sleep") as sleep, patch("sys.stdout", new_callable=io.StringIO):
                    self.assertEqual(main(["--url", "http://example"]), 0)
                snake.get_num_sims.assert_called_once_with()
                run.assert_called_once()
                db.close.assert_called_once_with()
                if num_sims == 0:
                    snake.submit_simulation.assert_called_once_with(GenerateDefaultConfig().run())
                    self.assertEqual([call.args[0] for call in db.log.call_args_list], [
                        "simulation_submitted", "golden_config_created", "simulation_started", "simulation_completed",
                    ])
                    self.assertEqual(db.log.call_args_list[0].args[3], "Submitted config.")
                    created = db.log.call_args_list[1]
                    self.assertEqual(created.args[1:4], (
                        "Configuration", "INFO", "Seeded database with default config.",
                    ))
                    self.assertEqual(created.kwargs["process_id"], snake.submit_simulation.return_value)
                    self.assertEqual(created.kwargs["parent_event_id"], db.log.return_value)
                    self.assertEqual(db.log.call_args_list[0].kwargs["process_id"], snake.submit_simulation.return_value)
                    self.assertEqual(sleep.call_count, 4)
                    self.assertTrue(all(call.args == (5,) for call in sleep.call_args_list))
                    self.assertEqual(db.log.call_args.args[3], "Simulation completed.")
                    snake.get_simulation_status.assert_called_with(snake.submit_simulation.return_value)
                else:
                    db.log.assert_not_called()
                    snake.submit_simulation.assert_not_called()
                    sleep.assert_not_called()

    def test_terminal_status_does_not_claim_running(self):
        initialize = runpy.run_path(str(ROOT / "ax3l/app/snakelab/main-loop.py"))["initialize_simulation"]
        for state in ("completed", "failed", "cancelled"):
            with self.subTest(state=state):
                db, snake = Mock(), Mock()
                snake.get_num_sims.return_value = 0
                snake.get_simulation_status.return_value = state
                with patch.dict(initialize.__globals__, {"SnakeLab": lambda: snake}), patch("time.sleep"):
                    initialize(db)
                self.assertEqual([call.args[0] for call in db.log.call_args_list], [
                    "simulation_submitted", "golden_config_created", f"simulation_{state}",
                ])

    def test_running_cycle_logs_start_once_and_closes_on_each_terminal_state(self):
        initialize = runpy.run_path(str(ROOT / "ax3l/app/snakelab/main-loop.py"))["initialize_simulation"]
        for state in ("completed", "failed", "cancelled"):
            with self.subTest(state=state):
                db, snake = Mock(), Mock()
                snake.get_num_sims.return_value = 0
                snake.submit_simulation.return_value = "f6e72cb3-9bcf-4669-b368-a17c656bad79"
                snake.get_simulation_status.side_effect = ["running", "paused", "running", state]
                with patch.dict(initialize.__globals__, {"SnakeLab": lambda: snake}), patch("time.sleep") as sleep:
                    initialize(db)
                self.assertEqual([call.args[0] for call in db.log.call_args_list], [
                    "simulation_submitted", "golden_config_created", "simulation_started", f"simulation_{state}",
                ])
                self.assertEqual(db.log.call_args.args[3], f"Simulation {state}.")
                self.assertEqual(db.log.call_args.args[2], "ERROR" if state == "failed" else "INFO")
                self.assertEqual(db.log.call_args.kwargs["process_id"], snake.submit_simulation.return_value)
                self.assertEqual(db.log.call_args.kwargs["parent_event_id"], db.log.return_value)
                self.assertEqual(sleep.call_count, 4)
                snake.submit_simulation.assert_called_once()

    def test_submission_failure_is_not_logged_as_submitted_or_retried(self):
        initialize = runpy.run_path(str(ROOT / "ax3l/app/snakelab/main-loop.py"))["initialize_simulation"]
        db, snake = Mock(), Mock()
        snake.get_num_sims.return_value = 0
        snake.submit_simulation.side_effect = TimeoutError()
        with patch.dict(initialize.__globals__, {"SnakeLab": lambda: snake}):
            with self.assertRaises(TimeoutError):
                initialize(db)
        snake.submit_simulation.assert_called_once()
        snake.get_simulation_status.assert_not_called()
        db.log.assert_not_called()

    def test_database_failure_stops_startup(self):
        main = runpy.run_path(str(ROOT / "ax3l/app/snakelab/main-loop.py"))["main"]
        db, snake, run, generator = Mock(), Mock(), Mock(), Mock()
        snake.get_num_sims.side_effect = RuntimeError("Database unavailable")
        with patch.dict(main.__globals__, {
            "DbMgr": lambda: db, "SnakeLab": lambda: snake,
            "run_first_iteration": run, "GenerateDefaultConfig": generator,
        }), patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(main(["--url", "http://example"]), 1)
        generator.assert_not_called()
        run.assert_not_called()
        db.close.assert_called_once_with()
