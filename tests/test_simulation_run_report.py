"""Simulation summary navigation and data lookup."""

from datetime import datetime
from threading import Thread
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import urlopen
from uuid import uuid4

from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb
from ax3l.server.ReportingServer import make_server


class SimulationRunReportTests(unittest.TestCase):
    def test_summary_lookup(self):
        db = Mock()
        run_id = str(uuid4())
        row = dict(run_id=run_id, project_version='0.14.0', high_score=0, completed_at=None)
        db.query.return_value = [row]
        self.assertEqual(SnakeLabDb(db).get_run_summary(run_id), row)
        sql, params = db.query.call_args.args
        self.assertIn('FROM simulation_runs WHERE run_id = %s', sql)
        self.assertEqual(params, (run_id,))
        db.query.return_value = []
        self.assertIsNone(SnakeLabDb(db).get_run_summary(run_id))

    def test_completed_link_and_summary(self):
        self.enterContext(patch('ax3l.server.ReportingServer.DbMgr'))
        log = self.enterContext(patch('ax3l.server.ReportingServer.EventLogDb')).return_value
        snake = self.enterContext(patch('ax3l.server.ReportingServer.SnakeLab')).return_value
        run_id = str(uuid4())
        snake.get_run_summary.return_value = dict(
            run_id=run_id, project_version='<version>', high_score=0,
            completed_at=datetime(2026, 9, 15, 12, 30, 45))
        event = dict(event_id=1, occurred_at=datetime.now(), log_level='INFO',
                     category='SnakeLab', name='simulation_completed', parameter=None,
                     process_id=run_id, content='Simulation completed.')
        log.recent.return_value = [event]
        server = make_server('127.0.0.1', 0)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        base = f'http://127.0.0.1:{server.server_port}'

        def get(path):
            with urlopen(base + path) as response:
                return response.read().decode()

        path = f'/simulations/{run_id}'
        self.assertIn(f'href="{path}">Simulation completed.</a>', get('/'))
        page = get(path)
        for expected in ('Simulation Run', 'Run ID', run_id, 'Project Version',
                         '&lt;version&gt;', 'High Score', '<td>0</td>', 'Completed At',
                         '2026-09-15 12:30:45', 'Back to event log'):
            self.assertIn(expected, page)
        self.assertNotIn('<version>', page)
        snake.get_run_summary.assert_called_with(run_id)
        snake.get_run_summary.return_value.update(high_score=None, completed_at=None)
        self.assertEqual(get(path).count('<td>—</td>'), 2)
        for category, name, process_id in (('Tool', 'simulation_completed', run_id),
                                           ('SnakeLab', 'simulation_failed', run_id),
                                           ('SnakeLab', 'simulation_completed', None)):
            event.update(category=category, name=name, process_id=process_id)
            self.assertNotIn(f'href="{path}"', get('/'))
        snake.get_run_summary.return_value = None
        for missing in (path, '/simulations/not-a-uuid'):
            with self.assertRaises(HTTPError) as error:
                get(missing)
            self.assertEqual(error.exception.code, 404)
