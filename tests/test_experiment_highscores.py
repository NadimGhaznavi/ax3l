import json
import os
from threading import Thread
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import urlopen

from ax3l.activity.ExperimentHighscores import highscores
from ax3l.app.experiment.ConfigurationLog import ConfigurationLog
from ax3l.interface.database.DbMgr import DbMgr
from ax3l.interface.database.EventLogDb import EventLogDb
from ax3l.server.ReportingServer import make_server


class HighscoreTests(unittest.TestCase):
    def test_rises_seed_drop_and_flat_tail(self):
        history = [dict(simulations=x, score=y, seed=seed, run_id=str(x), reason='Accepted', matched=False)
                   for x, y, seed in ((1, 38, 1), (3, 39, 1), (6, 50, 1), (12, 40, 2))]
        with patch('plotly.graph_objects.Figure.to_html', autospec=True,
                   side_effect=lambda figure, **kwargs: figure.to_json()):
            figure = json.loads(highscores(history, 15)['chart'])
        line, points, seed_points, matched_points = figure['data']
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
                         ['High score', 'Accepted config', 'Seed change', 'Matched high score'])
        self.assertEqual(matched_points['x'], [None])
        self.assertTrue(all(trace['showlegend'] for trace in figure['data']))
        self.assertIsNone(highscores([], 0)['chart'])
        self.assertIn('Plotly.newPlot', highscores([dict(simulations=1, score=0, seed=1,
                                                      run_id='a', reason='Initial', matched=False)], 1)['chart'])

    def test_ties_have_hover_details_without_changing_the_golden_line(self):
        history = [dict(simulations=x, score=y, seed=seed, run_id=f'{x}-run',
                        reason='Tie <details>' if matched else 'Accepted', matched=matched)
                   for x, y, seed, matched in (
                       (1, 50, 1, False), (3, 50, 1, True), (5, 60, 1, False),
                       (6, 60, 1, True), (8, 40, 2, False), (10, 40, 2, True))]
        with patch('plotly.graph_objects.Figure.to_html', autospec=True,
                   side_effect=lambda figure, **kwargs: figure.to_json()):
            figure = json.loads(highscores(history, 12)['chart'])
        line, accepted, seeds, matched = figure['data']
        self.assertEqual(line['x'], [1, 5, 8, 12])
        self.assertEqual(line['y'], [50, 60, 40, 40])
        self.assertEqual(accepted['x'], [1, 5])
        self.assertEqual(seeds['x'], [8])
        self.assertEqual(matched['x'], [3, 6, 10])
        self.assertEqual(matched['y'], [50, 60, 40])
        self.assertEqual(matched['marker']['color'], '#64c9a0')
        self.assertEqual(matched['customdata'][-1],
                         [2, '10', 'Tie &lt;details&gt;', '<br>Matched high score'])

    def test_seed_markers_require_consecutive_known_seeds(self):
        for seeds, expected in (
            ([7], ['#f09445']),
            ([None, 0, 0, 1, None, 2, 0],
             ['#f09445', '#f09445', '#f09445', '#c792ea', '#f09445', '#f09445', '#c792ea']),
        ):
            history = [dict(simulations=i + 1, score=10, seed=seed, run_id=str(i),
                            reason='Accepted', matched=False)
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
        ConfigurationLog(EventLogDb(db)).golden_config_created('run', reason='New seed', experiment_score=snapshot)
        self.assertEqual(db.execute.call_args.args[1], (4, 12, 40, 2))
        db._connection.commit.assert_called_once()
        db._connection.reset_mock()
        db.execute.side_effect = [1, 1, RuntimeError('write failed')]
        with self.assertRaises(RuntimeError):
            ConfigurationLog(EventLogDb(db)).golden_config_created('run', reason='New seed', experiment_score=snapshot)
        db._connection.commit.assert_not_called()
        db._connection.rollback.assert_called_once()


    def test_http_page_empty_and_failure(self):
        snake = self.enterContext(patch('ax3l.server.ReportingServer.SnakeLab')).return_value
        db = self.enterContext(patch('ax3l.app.reporting.Reports.DbMgr')).return_value
        snake.get_num_sims.return_value = 5
        db.query.return_value = [dict(simulations=1, score=38, seed=1, run_id='run',
                                     reason='Initial', matched=False),
                                 dict(simulations=3, score=38, seed=1, run_id='tie',
                                      reason='Same high score', matched=True)]
        server = make_server('127.0.0.1', 0)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f'http://127.0.0.1:{server.server_port}/experiment-highscores'
            with urlopen(url) as response:
                page = response.read().decode()
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertIn('Experiment Highscores', page)
            self.assertIn('Purple points mark seed changes. Orange points mark accepted configurations.', page)
            self.assertIn('green points and leave the golden unchanged.', page)
            self.assertIn('Matched high score', page)
            self.assertIn('Plotly.newPlot', page)
            self.assertNotIn('<script src=', page)
            db.close.assert_called_once()
            db.query.return_value = []
            with urlopen(url) as response:
                self.assertIn('No accepted scores recorded yet.', response.read().decode())
            db.query.side_effect = RuntimeError('offline')
            with patch('ax3l.interface.ReportHandler.logging.exception'), self.assertRaises(HTTPError) as error:
                urlopen(url)
            self.assertEqual(error.exception.code, 500)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


@unittest.skipUnless(os.environ.get('AX3L_TEST_DB') == '1', 'requires disposable MariaDB test database')
class HighscoreDatabaseTests(unittest.TestCase):
    def test_historical_ties_use_the_active_golden_score_and_seed(self):
        self.assertEqual(os.environ['DB_NAME'], 'ax3l_test')
        db = DbMgr()
        self.addCleanup(db.close)
        # Temporary tables isolate the fixture from stored experiment data.
        db.execute('''CREATE TEMPORARY TABLE events (
            event_id BIGINT PRIMARY KEY, category VARCHAR(50), name VARCHAR(100),
            process_id CHAR(36)
        ) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci''')
        db.execute('CREATE TEMPORARY TABLE event_messages (event_id BIGINT PRIMARY KEY, content LONGTEXT)')
        db.execute('''CREATE TEMPORARY TABLE experiment_highscores (
            event_id BIGINT PRIMARY KEY, simulations BIGINT, score INT, seed BIGINT)''')
        db.execute('''CREATE TEMPORARY TABLE snakelab.simulation_runs (
            id INT PRIMARY KEY, run_id CHAR(36) COLLATE utf8mb4_unicode_ci,
            high_score INT, status VARCHAR(20))''')
        db.execute('''CREATE TEMPORARY TABLE snakelab.configurations (
            run_id CHAR(36) COLLATE utf8mb4_unicode_ci PRIMARY KEY, seed BIGINT)''')

        def run(number, score, seed, status='completed'):
            run_id = f'run-{number}'
            # Gaps ensure simulation positions count stored rows, rather than IDs.
            db.execute('INSERT INTO snakelab.simulation_runs VALUES (%s, %s, %s, %s)',
                       (number * 10, run_id, score, status))
            db.execute('INSERT INTO snakelab.configurations VALUES (%s, %s)', (run_id, seed))

        def event(event_id, number, *, golden=False, category='Configuration'):
            name = 'golden_config_created' if golden else 'configuration_compared'
            db.execute('INSERT INTO events VALUES (%s, %s, %s, %s)',
                       (event_id, category, name, f'run-{number}'))
            reason = 'Initial baseline' if golden else json.dumps({'reason': f'Comparison {number}'})
            db.execute('INSERT INTO event_messages VALUES (%s, %s)', (event_id, reason))

        for number, score, seed, status in (
            (1, 50, 1, 'completed'), (2, 50, 1, 'completed'), (3, 40, 1, 'completed'),
            (4, 60, 1, 'completed'), (5, 60, 1, 'completed'), (6, 50, 1, 'completed'),
            (7, 40, 2, 'completed'), (8, 40, 2, 'completed'), (9, 40, 1, 'completed'),
            (10, 40, 2, 'failed'), (11, 40, 2, 'running'), (12, None, 2, 'completed'),
            (13, 40, 2, 'completed'), (14, 0, 3, 'completed'), (15, 0, 3, 'completed'),
        ):
            run(number, score, seed, status)
        for event_id, number, golden in (
            (1, 1, True), (2, 2, False), (3, 3, False), (4, 4, False), (5, 4, True),
            (6, 5, False), (7, 6, False), (8, 7, True), (9, 8, False), (10, 9, False),
            (11, 10, False), (12, 11, False), (13, 12, False), (14, 14, True), (15, 15, False),
        ):
            event(event_id, number, golden=golden)
        event(16, 15, category='Other')
        for event_id, simulations, score, seed in ((1, 1, 50, 1), (5, 4, 60, 1),
                                                   (8, 7, 40, 2), (14, 14, 0, 3)):
            db.execute('INSERT INTO experiment_highscores VALUES (%s, %s, %s, %s)',
                       (event_id, simulations, score, seed))

        history = EventLogDb(db).experiment_highscores()
        self.assertEqual([(row['simulations'], row['score'], row['seed'], row['matched']) for row in history],
                         [(1, 50, 1, 0), (2, 50, 1, 1), (4, 60, 1, 0), (5, 60, 1, 1),
                          (7, 40, 2, 0), (8, 40, 2, 1), (14, 0, 3, 0), (15, 0, 3, 1)])
        self.assertEqual(history[1]['run_id'], 'run-2')
        self.assertEqual(history[1]['reason'], 'Comparison 2')

        # Promoting a tie replaces its legacy match point with one golden point.
        event(17, 15, golden=True)
        db.execute('INSERT INTO experiment_highscores VALUES (17, 15, 0, 3)')
        promoted = [row for row in EventLogDb(db).experiment_highscores() if row['run_id'] == 'run-15']
        self.assertEqual(len(promoted), 1)
        self.assertEqual(promoted[0]['matched'], 0)
