"""HTTP integration check using the disposable DEV event database."""

import os
import json
from threading import Thread
import unittest
from urllib.request import urlopen
from urllib.error import HTTPError
from uuid import uuid4
from unittest.mock import patch


class ExperimentStatusTests(unittest.TestCase):
    def test_parameter_in_list_and_source_retained_in_detail(self):
        from datetime import datetime
        from pathlib import Path
        from jinja2 import Environment, FileSystemLoader, select_autoescape
        from ax3l.constants.DEventCategory import DEventCategory as Events

        templates = Environment(
            loader=FileSystemLoader(Path(__file__).parents[1] / 'ax3l/server/templates'),
            autoescape=select_autoescape(['html']))
        for parameter in ('learning_rate', 'epsilon_pair', 'reward_pair', None, '<unsafe>'):
            with self.subTest(parameter=parameter):
                event = dict(event_id=123, occurred_at=datetime.now(), log_level='INFO',
                             category='Conversation', name='prompt_sent', source_name='GoldenConfig',
                             parameter=parameter, content='Choose a value.', prompt_text='Choose a value.')
                page = templates.get_template('events.html').render(
                    events=[event], high_score=None, event_label=Events.label, event_choices={},
                    prompt_label='Prompt', simulation_events=Events.SnakeLab, request_timeout_seconds=10)
                self.assertIn('id="parameter-filter"', page)
                self.assertNotIn('source-filter', page)
                self.assertNotIn('GoldenConfig', page)
                expected = '&lt;unsafe&gt;' if parameter == '<unsafe>' else parameter or ''
                self.assertIn(f'class="parameter-column metadata" hidden>{expected}</td>', page)
                detail = templates.get_template('prompt.html').render(event=event, parts=[])
                self.assertIn('GoldenConfig', detail)
                self.assertIn(f'<td>{expected or "—"}</td>', detail)

    def test_prompt_detail_source_title_and_escaping(self):
        from ax3l.server.ReportingServer import make_server

        self.enterContext(patch('ax3l.server.ReportingServer.DbMgr'))
        log = self.enterContext(patch('ax3l.server.ReportingServer.EventLogDb')).return_value
        server = make_server('127.0.0.1', 0)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for source, title in (("GoldenConfig", "Prompt (GoldenConfig): #123"),
                                  ("<script>", "Prompt (&lt;script&gt;): #123"),
                                  (None, "Prompt: #123")):
                log.get.return_value = {
                    'event_id': 123, 'name': 'prompt_sent', 'category': 'Conversation',
                    'source_name': source,
                    'content': json.dumps({'role': 'user', 'content': 'Choose a value.'}),
                }
                with urlopen(f'http://127.0.0.1:{server.server_port}/events/123') as response:
                    page = response.read().decode()
                self.assertIn(f'<h1>{title}</h1>', page)
                self.assertIn(f'<title>{title} · Ax3l</title>', page)
                self.assertNotIn('<script>', page)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

    def test_status_counts_render_and_update(self):
        from ax3l.server.ReportingServer import make_server

        self.enterContext(patch('ax3l.server.ReportingServer.DbMgr'))
        log = self.enterContext(patch('ax3l.server.ReportingServer.EventLogDb')).return_value
        log.recent.return_value = []
        snake = self.enterContext(patch('ax3l.server.ReportingServer.SnakeLab')).return_value
        snake.is_simulation_running.return_value = False
        server = make_server('127.0.0.1', 0)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for submitted, cycles, score in ((0, 0, None), (17, 3, 60)):
                snake.get_num_sims.return_value = submitted
                snake.get_high_score.return_value = score
                log.experiment_cycles.return_value = cycles
                with urlopen(f'http://127.0.0.1:{server.server_port}/') as response:
                    page = response.read().decode()
                self.assertIn(f'Simulations Submitted: {submitted}', page)
                self.assertIn(f'Experiment Cycles: {cycles}', page)
                self.assertIn(f"Current Highscore: {score if score is not None else '—'}", page)
                self.assertIn('class="server-bar experiment-status"', page)
                self.assertIn('href="/score-distribution">Score Distribution Histogram</a>', page)
                self.assertIn('href="/experiment-highscores">Experiment Highscores</a>', page)
                self.assertIn('href="/golden-configurations">Golden Configurations</a>', page)
                self.assertLess(page.index('>Experiment Highscores</a>'),
                                page.index('>Golden Configurations</a>'))
                self.assertLess(page.index('>Score Distribution Histogram</a>'),
                                page.index('>Experiment Highscores</a>'))
                for element in ('simulations-submitted', 'experiment-cycles'):
                    self.assertIn(f"page.querySelector('#{element}').textContent", page)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


@unittest.skipUnless(os.environ.get("AX3L_TEST_DEV_DB") == "1", "requires DEV MariaDB")
class ReportingTests(unittest.TestCase):
    def test_log_page_refresh_and_escaping(self):
        self.assertEqual(os.environ["DB_NAME"], "ax3l_dev")
        from ax3l.app.DbMgr import DbMgr
        from ax3l.server.ReportingServer import make_server
        import zmq

        simulation = self.enterContext(patch(
            "ax3l.server.ReportingServer.SnakeLab.is_simulation_running", return_value=False,
        ))
        high_score = self.enterContext(patch(
            "ax3l.server.ReportingServer.SnakeLab.get_high_score", return_value=55,
        ))
        self.enterContext(patch(
            "ax3l.server.ReportingServer.SnakeLab.get_num_sims", return_value=17,
        ))

        db = DbMgr()
        process_id = str(uuid4())
        self.addCleanup(db.close)
        self.addCleanup(db.execute, "DELETE FROM events WHERE process_id = %s", (process_id,))
        first = f"{process_id} <script>alert('test')</script>\nNext line"
        db.log("report_test", "System", "INFO", first, process_id=process_id)
        server = make_server("127.0.0.1", 0)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}"
            with urlopen(url) as response:
                page = response.read().decode()
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                self.assertIn('<option value="0" selected>No Refresh</option>', page)
                self.assertNotIn("Refresh</button>", page)
                self.assertIn("&lt;script&gt;", page)
                self.assertNotIn("<script>alert('test')</script>", page)
                self.assertIn("Next line", page)
                self.assertIn("Snake Lab Server: Idle", page)
                self.assertIn("Current Highscore: 55", page)
                self.assertLess(page.index('id="snake-lab-status"'), page.index('id="experiment-status"'))
                self.assertLess(page.index('id="experiment-status"'), page.index('<h1>Ax3l Event Log'))
                self.assertLess(page.index('class="server-bar"'), page.index('<h1>Ax3l Event Log'))
            second = f"{process_id} refreshed event"
            simulation.return_value = True
            high_score.return_value = 60
            db.log("report_test", "System", "INFO", second, process_id=process_id)
            with urlopen(url) as response:
                page = response.read().decode()
                self.assertLess(page.index(second), page.index("&lt;script&gt;"))
                self.assertIn("Snake Lab Server: Running Simulation", page)
                self.assertIn("Current Highscore: 60", page)
            simulation.side_effect = zmq.Again()
            for _ in range(2):
                with urlopen(url) as response:
                    page = response.read().decode()
                    self.assertEqual(response.status, 200)
                    self.assertIn("Snake Lab Server: Service Unavailable", page)
                    self.assertIn("Current Highscore: 60", page)
                    self.assertIn(second, page)
                    self.assertIn('<option value="0" selected>No Refresh</option>', page)
            simulation.side_effect = None
            simulation.return_value = False
            with urlopen(url) as response:
                self.assertIn("Snake Lab Server: Idle", response.read().decode())
            for score, label in ((None, "—"), (0, "0")):
                high_score.return_value = score
                with urlopen(url) as response:
                    self.assertIn(f"Current Highscore: {label}", response.read().decode())
            with urlopen(url + "/health") as response:
                self.assertEqual(response.status, 200)

            reply_text = "Quiet <script>night</script>\nA tree's shade"
            payload = {
                "choices": [{"index": 0, "finish_reason": "stop", "message": {
                    "role": "assistant", "content": reply_text,
                }}],
                "model": "Qwen2.5-VL", "id": "chatcmpl-test",
                "usage": {"prompt_tokens": 24, "prompt_tokens_details": {"cached_tokens": 0}},
                "timings": {"predicted_ms": 946.36},
                "extra": {"flag": False, "empty": [], "missing": None},
            }
            event_id = db.log("reply_received", "Conversation", "INFO", json.dumps(payload), process_id=process_id)
            with urlopen(url) as response:
                page = response.read().decode()
                self.assertIn(f'href="/events/{event_id}">Quiet &lt;script&gt;night&lt;/script&gt;', page)
                self.assertNotIn("chatcmpl-test", page)
            with urlopen(f"{url}/events/{event_id}") as response:
                page = response.read().decode()
                self.assertIn("Quiet &lt;script&gt;night&lt;/script&gt;", page)
                self.assertNotIn("<script>", page)
                for value in ("usage.prompt_tokens_details.cached_tokens", "timings.predicted_ms", "946.36", "chatcmpl-test", "choices[0].finish_reason", "extra.flag", "false", "extra.empty", "[]", "null"):
                    self.assertIn(value, page)
            png_url = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a4WQAAAAASUVORK5CYII="
            for caption in ("Per-episode loss <script>test</script>", "Golden versus latest loss"):
                prompt = {"role": "user", "content": [
                    {"type": "text", "text": caption},
                    {"type": "image_url", "image_url": {"url": png_url}},
                ]}
                prompt_id = db.log("prompt_sent", "Conversation", "INFO", json.dumps(prompt),
                                   process_id=process_id, source_name="ComparisonPlot")
                with urlopen(url) as response:
                    page = response.read().decode()
                    self.assertIn(f'href="/events/{prompt_id}"', page)
                    self.assertNotIn(png_url, page)
                with patch("ax3l.interface.SnakeLab.SnakeLab.get_episode_losses", side_effect=AssertionError("Must use logged snapshot")):
                    with urlopen(f"{url}/events/{prompt_id}") as response:
                        page = response.read().decode()
                self.assertIn(f'<img src="{png_url}"', page)
                self.assertIn(f'Prompt (ComparisonPlot): #{prompt_id}', page)
                self.assertNotIn('<script>test</script>', page)
                self.assertIn('Back to event log', page)
            text_id = db.log("prompt_sent", "Conversation", "INFO",
                             json.dumps({"role": "user", "content": "Choose a learning rate."}), process_id=process_id)
            with urlopen(f"{url}/events/{text_id}") as response:
                page = response.read().decode()
                self.assertIn('Choose a learning rate.', page)
                self.assertNotIn('<img', page)
            with self.assertRaises(HTTPError) as error:
                urlopen(url + "/events/0")
            self.assertEqual(error.exception.code, 404)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
