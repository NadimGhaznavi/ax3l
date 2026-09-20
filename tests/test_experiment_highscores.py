import json
import runpy
from pathlib import Path
from threading import Thread
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import urlopen

from ax3l.activity.ExperimentHighscores import highscores
from ax3l.app.ConfigurationLog import ConfigurationLog
from ax3l.app.DbMgr import DbMgr
from ax3l.server.ReportingServer import make_server


class HighscoreTests(unittest.TestCase):
    def test_rises_seed_drop_and_flat_tail(self):
        history = [dict(simulations=x, score=y, seed=seed, run_id=str(x), reason='Accepted')
                   for x, y, seed in ((1, 38, 1), (3, 39, 1), (6, 50, 1), (12, 40, 2))]
        with patch('plotly.graph_objects.Figure.to_html', autospec=True,
                   side_effect=lambda figure, **kwargs: figure.to_json()):
            figure = json.loads(highscores(history, 15)['chart'])
        line, points, seed_points = figure['data']
        self.assertEqual(line['x'], [1, 3, 6, 12, 15])
        self.assertEqual(line['y'], [38, 39, 50, 40, 40])
        self.assertEqual(line['line']['shape'], 'spline')
        self.assertEqual(seed_points['customdata'][-1][0], 2)
        self.assertEqual(points['x'], [1, 3, 6])
        self.assertEqual(seed_points['x'], [12])
        self.assertEqual(seed_points['y'], [40])
        self.assertEqual(line['line']['color'], '#4c9be8')
        self.assertEqual(points['marker']['color'], '#f09445')
        self.assertEqual(seed_points['marker']['color'], '#c792ea')
        self.assertEqual(seed_points['customdata'][0][3], '<br>Seed change')
        self.assertEqual([trace['name'] for trace in figure['data']],
                         ['High score', 'Accepted config', 'Seed change'])
        self.assertTrue(all(trace['showlegend'] for trace in figure['data']))
        self.assertIsNone(highscores([], 0)['chart'])
        self.assertIn('Plotly.newPlot', highscores([dict(simulations=1, score=0, seed=1,
                                                      run_id='a', reason='Initial')], 1)['chart'])

    def test_seed_markers_require_consecutive_known_seeds(self):
        for seeds, expected in (
            ([7], ['#f09445']),
            ([None, 0, 0, 1, None, 2, 0],
             ['#f09445', '#f09445', '#f09445', '#c792ea', '#f09445', '#f09445', '#c792ea']),
        ):
            history = [dict(simulations=i + 1, score=10, seed=seed, run_id=str(i), reason='Accepted')
                       for i, seed in enumerate(seeds)]
            with patch('plotly.graph_objects.Figure.to_html', autospec=True,
                       side_effect=lambda figure, **kwargs: figure.to_json()):
                figure = json.loads(highscores(history, len(history))['chart'])
            for trace, color in zip(figure['data'][1:], ['#f09445', '#c792ea']):
                self.assertEqual(trace['marker']['color'], color)
                self.assertEqual(trace['x'], [i + 1 for i, value in enumerate(expected) if value == color] or [None])

    def test_snapshot_commits_with_event_and_rolls_back_on_failure(self):
        db = object.__new__(DbMgr)
        db._connection = Mock()
        db.execute = Mock()
        db.query = Mock(return_value=[{'event_id': 4}])
        snapshot = {'simulations': 12, 'score': 40, 'seed': 2}
        ConfigurationLog(db).golden_config_created('run', reason='New seed', experiment_score=snapshot)
        self.assertEqual(db.execute.call_args.args[1], (4, 12, 40, 2))
        db._connection.commit.assert_called_once()
        db._connection.reset_mock()
        db.execute.side_effect = [1, 1, RuntimeError('write failed')]
        with self.assertRaises(RuntimeError):
            ConfigurationLog(db).golden_config_created('run', reason='New seed', experiment_score=snapshot)
        db._connection.commit.assert_not_called()
        db._connection.rollback.assert_called_once()

    def test_initial_baseline_and_restart_record_only_completed_score(self):
        initialize = runpy.run_path(str(Path('ax3l/app/snakelab/main-loop.py')))['initialize_simulation']
        for resume in (False, True):
            snake, db = Mock(), Mock()
            snake.get_num_sims.side_effect = [1 if resume else 0, 1]
            snake.submit_simulation.return_value = 'initial'
            snake.get_simulation_status.return_value = 'completed'
            snake.get_run_result.return_value = {'high_score': 38, 'config': {'seed': 7}}
            db.query.side_effect = [[], [{'event_id': 1, 'process_id': 'initial'}]]
            with patch.dict(initialize.__globals__, {'SnakeLab': lambda: snake}), patch('time.sleep'):
                initialize(db)
            call = db.log.call_args
            self.assertEqual(call.args[0], 'golden_config_created')
            self.assertEqual(call.kwargs['experiment_score'], {'simulations': 1, 'score': 38, 'seed': 7})
            if resume:
                snake.submit_simulation.assert_not_called()

    def test_http_page_empty_and_failure(self):
        snake = self.enterContext(patch('ax3l.server.ReportingServer.SnakeLab')).return_value
        db = self.enterContext(patch('ax3l.server.ReportingServer.DbMgr')).return_value
        snake.get_num_sims.return_value = 5
        db.query.return_value = [dict(simulations=1, score=38, seed=1, run_id='run', reason='Initial')]
        server = make_server('127.0.0.1', 0)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f'http://127.0.0.1:{server.server_port}/experiment-highscores'
            with urlopen(url) as response:
                page = response.read().decode()
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertIn('Experiment Highscores', page)
            self.assertIn('Purple points mark seed changes. Other points are orange.', page)
            self.assertIn('Plotly.newPlot', page)
            self.assertNotIn('<script src=', page)
            db.close.assert_called_once()
            db.query.return_value = []
            with urlopen(url) as response:
                self.assertIn('No accepted scores recorded yet.', response.read().decode())
            db.query.side_effect = RuntimeError('offline')
            with patch('ax3l.server.ReportingServer.traceback.print_exc'), self.assertRaises(HTTPError) as error:
                urlopen(url)
            self.assertEqual(error.exception.code, 500)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
