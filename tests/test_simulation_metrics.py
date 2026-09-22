"""Simulation runtime plots and their MariaDB timing joins."""

from datetime import datetime, timedelta
import json
import os
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from ax3l.activity.SimulationMetrics import metrics
from ax3l.app.DbMgr import DbMgr
from ax3l.app.EventLogDb import EventLogDb


class MetricsReportTests(unittest.TestCase):
    def test_lines_numbering_units_and_missing_timings(self):
        with patch('plotly.graph_objects.Figure.to_html', autospec=True, return_value='chart') as html:
            result = metrics([
                dict(run_id='baseline', runtime_seconds=100, llm_seconds=0),
                dict(run_id='retry', runtime_seconds=50, llm_seconds=12.5),
                dict(run_id='missing', runtime_seconds=60, llm_seconds=None),
            ])
            figure = html.call_args.args[0]
        self.assertEqual(result, {'chart': 'chart', 'total': 3})
        self.assertEqual([trace.name for trace in figure.data], ['Simulation Runtime', 'LLM Time'])
        for trace in figure.data:
            self.assertEqual(list(trace.x), [1, 2, 3])
            self.assertEqual(trace.line.shape, 'spline')
        self.assertEqual(list(figure.data[0].y), [100, 50, 60])
        self.assertEqual(list(figure.data[1].y), [0, 12.5, None])
        self.assertFalse(figure.data[1].connectgaps)
        self.assertEqual(figure.layout.yaxis.title.text, 'Time (seconds)')
        self.assertEqual(metrics([]), {'chart': None, 'total': 0})

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
        log.simulation_metrics.return_value = [dict(run_id='run', runtime_seconds=10, llm_seconds=2)]
        with urlopen(url) as response:
            page = response.read().decode()
        self.assertIn('id="simulation-runtime"', page)
        self.assertIn('Simulation Runtime', page)
        self.assertIn('LLM Time', page)
        log.simulation_metrics.side_effect = RuntimeError('database unavailable')
        with patch('ax3l.server.ReportingServer.traceback.print_exc'), self.assertRaises(HTTPError) as error:
            urlopen(url)
        self.assertEqual(error.exception.code, 500)
        self.assertEqual(db.close.call_count, 3)


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
            status VARCHAR(20), started_at DATETIME(6), completed_at DATETIME(6))''')
        start = datetime(2026, 9, 22)
        for id, run, status, offset, duration in (
            (1, 'baseline', 'completed', 0, 10),
            (2, 'failed', 'failed', 10, 1),
            (3, 'running', 'running', 20, None),
            (4, 'retry', 'completed', 30, 20),
            (5, 'missing', 'completed', 60, 10),
            (6, 'cancelled', 'cancelled', 80, 1),
        ):
            db.execute('INSERT INTO snakelab.simulation_runs VALUES (%s,%s,%s,%s,%s)',
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
