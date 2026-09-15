"""Simulation summary navigation and data lookup."""

from datetime import datetime
import json
from xml.etree.ElementTree import fromstring
from threading import Thread
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import urlopen
from uuid import uuid4

from ax3l.app.snakelab.SnakeLabDb import SnakeLabDb
from ax3l.server.ReportingServer import make_server
from ax3l.activity.SimulationBoard import board_svg


SNAPSHOT = {"board": {"grid_size": [4, 3], "snake_head": [2, 1],
                      "snake_body": [[1, 1], [0, 1]], "food": [3, 2]}}


class SimulationRunReportTests(unittest.TestCase):
    def test_board_geometry_and_missing_snapshots(self):
        svg = fromstring(board_svg(json.dumps(SNAPSHOT)))
        ns = {'svg': 'http://www.w3.org/2000/svg'}
        self.assertEqual(svg.attrib['viewBox'], '0 0 128 96')
        self.assertEqual(len(svg.findall('svg:line', ns)), 9)
        rectangles = svg.findall('svg:rect', ns)
        self.assertEqual(len(rectangles), 4)
        self.assertEqual((rectangles[-1].attrib['x'], rectangles[-1].attrib['y']), ('65', '33'))
        food = svg.find('svg:circle', ns)
        self.assertEqual((food.attrib['cx'], food.attrib['cy']), ('112.0', '80.0'))
        full = {'board': {**SNAPSHOT['board'], 'food': None}}
        self.assertIsNone(fromstring(board_svg(full)).find('svg:circle', ns))
        for invalid in (None, 'invalid JSON', {}, {'board': {'grid_size': ['<script>', 3]}},
                        {'board': {**SNAPSHOT['board'], 'snake_head': [-1, 0]}}):
            self.assertIsNone(board_svg(invalid))

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
        log.current_golden_config.return_value = None
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
        self.assertIn('No saved board is available', page)
        snake.get_run_summary.return_value['high_score_snapshot'] = json.dumps(SNAPSHOT)
        board_page = get(path)
        self.assertIn('<svg ', board_page)
        self.assertIn('viewBox="0 0 128 96"', board_page)
        self.assertNotIn('No saved board is available', board_page)
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
