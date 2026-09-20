"""Score cohorts and HTTP rendering, without a live Snake Lab database."""

import json
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from ax3l.activity.ScoreDistribution import distribution
from ax3l.interface.SnakeLab import SnakeLab
from ax3l.server.ReportingServer import make_server


class ScoreDistributionTests(unittest.TestCase):
    def figure(self, scores):
        with patch('plotly.graph_objects.Figure.to_html', autospec=True,
                   side_effect=lambda figure, **kwargs: figure.to_json()):
            result = distribution(scores)
        return result, json.loads(result['chart'])

    def test_cumulative_thirds_before_filtering_and_shared_bins(self):
        result, figure = self.figure([0, None, 2, 100, 100, 9, 9])
        self.assertEqual((result['total'], result['third'], result['two_thirds']), (7, 2, 4))
        self.assertEqual((result['scored'], result['older_scored'], result['oldest_scored']), (6, 3, 1))
        all_runs, older, oldest = figure['data']
        self.assertEqual(all_runs['x'], [0, 2, 100, 100, 9, 9])
        self.assertEqual(older['x'], [0, 2, 100])
        self.assertEqual(oldest['x'], [0])
        self.assertEqual(all_runs['xbins'], older['xbins'])
        self.assertEqual(all_runs['xbins'], oldest['xbins'])
        self.assertEqual([trace['marker']['color'] for trace in figure['data']],
                         ['#4c9be8', '#f09445', '#b86b6b'])
        self.assertEqual([trace['name'] for trace in figure['data']],
                         ['All runs (3/3)', 'Oldest two-thirds (2/3)', 'Oldest third (1/3)'])
        self.assertEqual(figure['layout']['barmode'], 'overlay')
        bins = all_runs['xbins']
        counts = []
        for trace in figure['data']:
            tally = {}
            for score in trace['x']:
                bucket = int((score - bins['start']) // bins['size'])
                tally[bucket] = tally.get(bucket, 0) + 1
            counts.append(tally)
        for larger, smaller in zip(counts, counts[1:]):
            self.assertTrue(all(count <= larger[bucket] for bucket, count in smaller.items()))

    def test_empty_single_and_identical_scores(self):
        for scores in ([], [None, None]):
            self.assertIsNone(distribution(scores)['chart'])
        for scores, expected_older, expected_oldest in (
            ([0], [], []), ([1, 2], [1], []),
            ([7] * 4, [7] * 2, [7]), ([7] * 5, [7] * 3, [7]),
            ([7] * 6, [7] * 4, [7] * 2),
        ):
            _, figure = self.figure(scores)
            self.assertEqual(figure['data'][1]['x'], expected_older)
            self.assertEqual(figure['data'][2]['x'], expected_oldest)
            self.assertEqual(figure['data'][0]['xbins']['size'], 1)

    def test_interface_orders_all_runs_and_closes_connection(self):
        with patch('ax3l.interface.SnakeLab.DbMgr') as db_class:
            db = db_class.return_value
            db.query.return_value = [{'high_score': None}, {'high_score': 0}, {'high_score': 20}]
            self.assertEqual(SnakeLab().get_run_scores(), [None, 0, 20])
            db.query.assert_called_once_with('SELECT high_score FROM simulation_runs ORDER BY id')
            self.assertFalse(db_class.call_args.kwargs['initialize_event_tables'])
            db.close.assert_called_once()
            db.close.reset_mock()
            db.query.side_effect = RuntimeError('offline')
            with self.assertRaises(RuntimeError):
                SnakeLab().get_run_scores()
            db.close.assert_called_once()

    def test_http_page_and_empty_and_failure(self):
        snake = self.enterContext(patch('ax3l.server.ReportingServer.SnakeLab')).return_value
        server = make_server('127.0.0.1', 0)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f'http://127.0.0.1:{server.server_port}/score-distribution'
            snake.get_run_scores.return_value = [0, 4, 9, None]
            with urlopen(url) as response:
                page = response.read().decode()
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertIn('All runs (3/3): 4 (3 scored).', page)
            self.assertIn('Oldest two-thirds (2/3): 2 (2 scored).', page)
            self.assertIn('Oldest third (1/3): 1 (1 scored).', page)
            self.assertIn('Plotly.newPlot', page)
            self.assertIn('id="score-histogram"', page)
            self.assertNotIn('<script src=', page)
            self.assertIn('Back to event log', page)
            snake.get_run_scores.return_value = []
            with urlopen(url) as response:
                self.assertIn('No scores recorded yet.', response.read().decode())
            snake.get_run_scores.side_effect = RuntimeError('offline')
            with patch('ax3l.server.ReportingServer.traceback.print_exc'):
                with self.assertRaises(HTTPError) as error:
                    urlopen(url)
            self.assertEqual(error.exception.code, 500)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
