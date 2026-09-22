"""Simulation runtime plots and their MariaDB timing joins."""

from datetime import datetime, timedelta
import json
import os
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from ax3l.activity.SimulationMetrics import buckets, metrics
from ax3l.app.DbMgr import DbMgr
from ax3l.app.EventLogDb import EventLogDb


class MetricsReportTests(unittest.TestCase):
    def test_consecutive_buckets_statistics_and_partial_tail(self):
        rows = [dict(runtime_seconds=i * 10, llm_seconds=i, high_score=i,
                     total_steps=i * 100, steps_per_episode=i * 5) for i in range(1, 42)]
        summaries = buckets(rows, 20)
        self.assertEqual([(b['first'], b['last'], b['count']) for b in summaries],
                         [(1, 20, 20), (21, 40, 20), (41, 41, 1)])
        self.assertEqual(sum(b['count'] for b in summaries), len(rows))
        self.assertEqual([b['runtime_seconds'] for b in summaries], [105, 305, 410])
        self.assertEqual(summaries[0]['high_score'], 10.5)
        self.assertEqual(summaries[0]['median_high_score'], 10.5)
        self.assertEqual(summaries[0]['total_steps'], 1050)
        self.assertEqual(summaries[0]['steps_per_episode'], 52.5)
        for size, expected in ((10, 5), (20, 3), (50, 1)):
            self.assertEqual(len(buckets(rows, size)), expected)
        self.assertEqual(buckets(rows[:40], 20)[-1]['count'], 20)
        with patch('plotly.graph_objects.Figure.to_html', autospec=True, return_value='chart') as html:
            result = metrics(rows)
            figure = html.call_args_list[0].args[0]
            steps_figure = html.call_args_list[1].args[0]
        self.assertEqual(result['bucket_size'], 20)
        self.assertEqual(result['bucket_count'], 3)
        self.assertEqual([trace.name for trace in figure.data], ['Simulation Runtime', 'LLM Time'])
        for trace in figure.data:
            self.assertEqual(list(trace.x), [1, 2, 3])
            self.assertEqual(trace.line.shape, 'spline')
        self.assertEqual(list(figure.data[0].y), [105 / 60, 305 / 60, 410 / 60])
        self.assertEqual(list(figure.data[1].y), [10.5 / 60, 30.5 / 60, 41 / 60])
        self.assertEqual(figure.layout.yaxis.title.text, 'Mean time (minutes)')
        self.assertEqual(list(steps_figure.data[0].x), [1, 2, 3])
        self.assertEqual(list(steps_figure.data[0].y), [1050, 3050, 4100])
        self.assertEqual(steps_figure.data[0].line.shape, 'spline')
        self.assertEqual(steps_figure.layout.xaxis.title, figure.layout.xaxis.title)
        self.assertIn('min', figure.data[0].hovertemplate)
        self.assertTrue(html.call_args_list[0].kwargs['include_plotlyjs'])
        self.assertFalse(html.call_args_list[1].kwargs['include_plotlyjs'])
        self.assertIsNone(metrics([])['chart'])
        self.assertIsNone(metrics([])['steps_chart'])

    def test_missing_metrics_do_not_drop_runs_or_become_zero(self):
        rows = [dict(runtime_seconds=10, llm_seconds=0, high_score=0,
                     total_steps=100, steps_per_episode=50),
                dict.fromkeys(('runtime_seconds', 'llm_seconds', 'high_score',
                               'total_steps', 'steps_per_episode'))]
        bucket = buckets(rows, 20)[0]
        self.assertEqual(bucket['count'], 2)
        self.assertEqual(bucket['runtime_seconds'], 10)
        self.assertEqual(bucket['runtime_seconds_count'], 1)
        self.assertEqual(bucket['high_score'], 0)
        self.assertEqual(bucket['llm_seconds'], 0)
        self.assertIsNone(buckets(rows[1:], 20)[0]['runtime_seconds'])
        with patch('plotly.graph_objects.Figure.to_html', autospec=True, return_value='chart') as html:
            metrics(rows, 1)
            steps_figure = html.call_args_list[1].args[0]
        self.assertEqual(list(steps_figure.data[0].y), [100, None])
        self.assertFalse(steps_figure.data[0].connectgaps)

    def test_page_empty_state_and_database_cleanup(self):
        from ax3l.server.ReportingServer import make_server
        db = self.enterContext(patch('ax3l.server.ReportingServer.DbMgr')).return_value
        log = self.enterContext(patch('ax3l.server.ReportingServer.EventLogDb')).return_value
        log.simulation_metrics.return_value = []
        server = make_server('127.0.0.1', 0)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        url = f'http://127.0.0.1:{server.server_port}/simulation-metrics'
        with urlopen(url) as response:
            page = response.read().decode()
        self.assertIn('No successfully completed simulations', page)
        self.assertIn('class="chart-page"', page)
        db.close.assert_called_once()
        log.simulation_metrics.return_value = [dict(run_id='run', runtime_seconds=10, llm_seconds=2, high_score=3, total_steps=100, steps_per_episode=50)]
        with urlopen(url) as response:
            page = response.read().decode()
        self.assertIn('id="simulation-runtime"', page)
        self.assertIn('id="steps-per-simulation"', page)
        self.assertIn('<h2>Steps per Simulation</h2>', page)
        self.assertIn('Simulation Runtime', page)
        self.assertIn('LLM Time', page)
        for size in (10, 20, 50, 7):
            with urlopen(url + f'?bucket_size={size}') as response:
                self.assertIn(f'value="{size}"', response.read().decode())
        for value in ('0', '-1', 'abc', '1.5', '', '10&bucket_size=20'):
            with self.assertRaises(HTTPError) as error:
                urlopen(url + '?bucket_size=' + value)
            self.assertEqual(error.exception.code, 400)
        log.simulation_metrics.side_effect = RuntimeError('database unavailable')
        with patch('ax3l.server.ReportingServer.traceback.print_exc'), self.assertRaises(HTTPError) as error:
            urlopen(url)
        self.assertEqual(error.exception.code, 500)
        self.assertEqual(db.close.call_count, 7)


@unittest.skipUnless(os.environ.get('AX3L_TEST_DEV_DB') == '1', 'requires disposable DEV MariaDB')
class MetricsDatabaseTests(unittest.TestCase):
    def test_completed_runs_retries_and_context_messages(self):
        self.assertEqual(os.environ['DB_NAME'], 'ax3l_dev')
        db = DbMgr()
        self.addCleanup(db.close)
        # Temporary tables keep the fixture separate from stored experiment data.
        db.execute('''CREATE TEMPORARY TABLE events (
            event_id BIGINT AUTO_INCREMENT PRIMARY KEY, occurred_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
            name VARCHAR(100), category VARCHAR(50), log_level VARCHAR(10), process_id CHAR(36),
            parent_event_id BIGINT, source_name VARCHAR(255), parameter VARCHAR(100), ax3l_version VARCHAR(100)
        ) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci''')
        db.execute('CREATE TEMPORARY TABLE event_messages (event_id BIGINT PRIMARY KEY, content LONGTEXT)')
        db.execute('''CREATE TEMPORARY TABLE snakelab.simulation_runs (
            id INT PRIMARY KEY, run_id CHAR(36) COLLATE utf8mb4_unicode_ci,
            high_score INT DEFAULT 10, status VARCHAR(20), started_at DATETIME(6), completed_at DATETIME(6))''')
        db.execute('''CREATE TEMPORARY TABLE snakelab.simulation_episodes (
            run_id CHAR(36) COLLATE utf8mb4_unicode_ci, episode INT, steps INT)''')
        db.execute("INSERT INTO snakelab.simulation_episodes VALUES ('retry', 1, 100), ('retry', 2, 300)")
        start = datetime(2026, 9, 22)
        for id, run, status, offset, duration in (
            (1, 'baseline', 'completed', 0, 10),
            (2, 'failed', 'failed', 10, 1),
            (3, 'running', 'running', 20, None),
            (4, 'retry', 'completed', 30, 20),
            (5, 'missing', 'completed', 60, 10),
            (6, 'cancelled', 'cancelled', 80, 1),
        ):
            db.execute('INSERT INTO snakelab.simulation_runs (id, run_id, status, started_at, completed_at) VALUES (%s,%s,%s,%s,%s)',
                       (id, run, status, start + timedelta(seconds=offset),
                        start + timedelta(seconds=offset + duration) if duration is not None else None))

        def event(name, seconds, process='conversation', category='Conversation', content='{}'):
            id = db.log(name, category, 'INFO', content, process_id=process)
            db.execute('UPDATE events SET occurred_at=%s WHERE event_id=%s',
                       (start + timedelta(seconds=seconds), id))

        event('prompt_sent', 1)  # Context and user prompt are a single request.
        event('prompt_sent', 2)
        event('reply_received', 4.5)  # 2.5 seconds, not 6 seconds.
        event('tool_execution_completed', 5, category='Tool', content='{"status":"rejected"}')
        event('prompt_sent', 10)
        event('reply_received', 11, process='unrelated')
        event('reply_received', 20)  # Retry adds 10 seconds; tool time is excluded.
        event('tool_execution_completed', 21, category='Tool',
              content=json.dumps({'status': 'ok', 'run_id': 'retry'}))
        event('tool_execution_completed', 22, category='Tool', content='invalid JSON')
        event('reply_received', 25, process='missing-conversation')
        event('tool_execution_completed', 26, process='missing-conversation', category='Tool',
              content=json.dumps({'status': 'ok', 'run_id': 'missing'}))
        rows = EventLogDb(db).simulation_metrics()
        self.assertEqual([row['run_id'] for row in rows], ['baseline', 'retry', 'missing'])
        self.assertEqual([float(row['runtime_seconds']) for row in rows], [10, 20, 10])
        self.assertEqual(float(rows[0]['llm_seconds']), 0)
        self.assertEqual(float(rows[1]['llm_seconds']), 12.5)
        self.assertIsNone(rows[2]['llm_seconds'])
        self.assertEqual(rows[1]['total_steps'], 400)
        self.assertEqual(rows[1]['steps_per_episode'], 200)
        self.assertIsNone(rows[0]['total_steps'])
        self.assertEqual(rows[1]['high_score'], 10)
