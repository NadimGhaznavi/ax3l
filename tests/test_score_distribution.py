"""Check cumulative GIF frames, encoded frames, shared scales, and HTTP rendering."""
from io import BytesIO
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from ax3l.activity.ScoreDistribution import distribution_frames, render_distribution, PLOT


class ScoreDistributionTests(unittest.TestCase):
    def test_2054_simulations_have_four_cumulative_checkpoints_and_all_runs(self):
        scores = {number: number % 20 for number in range(1, 2055)}
        frames = distribution_frames(scores)
        self.assertEqual(len(frames), 6)
        self.assertEqual(frames[0], ('Before simulation #1', []))
        self.assertEqual(frames[1][0], 'Simulations #1–500')
        self.assertEqual(frames[2][0], 'Simulations #1–1000')
        self.assertEqual(frames[-2][0], 'Simulations #1–2000')
        self.assertEqual(frames[-1][0], 'All simulations #1–2054')
        self.assertEqual([len(values) for _, values in frames[1:-1]], [500, 1000, 1500, 2000])
        for index, (_, values) in enumerate(frames[1:-1], 1):
            self.assertEqual(values, [scores[number] for number in range(1, index * 500 + 1)])
        self.assertEqual(len(frames[-1][1]), 2054)
        gif = Image.open(BytesIO(render_distribution(scores)))
        self.assertEqual(gif.n_frames, 6)
        self.assertEqual(gif.info['loop'], 0)
        self.assertEqual(gif.size, (800, 480))
        for index in range(6):
            gif.seek(index)
            self.assertEqual(gif.info['duration'], 5000 if index == 5 else 2000)
            self.assertEqual(gif.disposal_method, 2)

    def test_fixed_axes_bar_positions_and_embedded_labels(self):
        # Cumulative bars grow while both axes stay fixed through the final frame.
        scores = {number: 0 if number % 2 else 10 for number in range(1, 1001)}
        labels = []
        font_sizes = {}
        original = ImageDraw.ImageDraw.text
        def record(draw, xy, text, *args, **kwargs):
            labels.append(text)
            font_sizes[text] = kwargs['font'].size
            return original(draw, xy, text, *args, **kwargs)
        with patch.object(ImageDraw.ImageDraw, 'text', record):
            data = render_distribution(scores)
        self.assertIn('Simulations #1–1000', labels)
        self.assertIn('1,000 submitted · 1,000 scored', labels)
        self.assertIn('Number of runs', labels)
        self.assertIn('Run high score', labels)
        self.assertEqual(font_sizes['Number of runs'], 15)
        self.assertEqual(font_sizes['Score Distribution'], 17)
        self.assertEqual(font_sizes['Simulations #1–1000'], 14)
        self.assertEqual(font_sizes['Run high score'], 14)
        self.assertEqual(font_sizes['1,000 submitted · 1,000 scored'], 12)
        self.assertEqual(font_sizes['200'], 11)
        self.assertIn('500', labels)
        gif = Image.open(BytesIO(data))
        images = []
        for index in range(gif.n_frames):
            gif.seek(index)
            images.append(gif.convert('RGB'))
        for image in images[1:]:
            self.assertEqual(image.crop((90, 351, 775, 430)).tobytes(),
                             images[0].crop((90, 351, 775, 430)).tobytes())
        for image in images[1:]:
            self.assertEqual(image.crop((0, 110, 90, 351)).tobytes(),
                             images[0].crop((0, 110, 90, 351)).tobytes())
        x = int(PLOT[0] + .5 * (PLOT[2] - PLOT[0]) / 11)
        blue = (76, 155, 232)
        self.assertNotEqual(images[0].getpixel((x, 300)), blue)
        self.assertEqual(images[1].getpixel((x, 300)), blue)
        self.assertNotEqual(images[1].getpixel((x, 150)), blue)
        self.assertEqual(images[-1].getpixel((x, 150)), blue)
        self.assertEqual(data, render_distribution(scores))

    def test_null_zero_and_incomplete_id_blocks(self):
        scores = {1: 9, 2: 0}
        self.assertEqual(distribution_frames(scores)[-1][1], [9, 0])
        missing = {number: None for number in range(1, 1001) if number != 50}
        frames = distribution_frames(missing)
        self.assertEqual(len(frames), 3)
        self.assertEqual(frames[1][0], 'Simulations #1–1000')
        self.assertEqual(len(frames[1][1]), 999)
        for scores in ({}, {1: None}, {1: 0}, missing):
            gif = Image.open(BytesIO(render_distribution(scores)))
            self.assertEqual(gif.n_frames, len(distribution_frames(scores)))
            gif.seek(gif.n_frames - 1)
            self.assertEqual(gif.info['duration'], 5000)

    def test_final_y_scale_includes_partial_block_and_is_used_throughout(self):
        scores = {number: number % 50 for number in range(1, 501)}
        scores.update({number: number % 25 for number in range(501, 1001)})
        scores.update({number: 0 for number in range(1001, 1100)})
        ticks = []
        original = ImageDraw.ImageDraw.text
        def record(draw, xy, text, *args, **kwargs):
            if text == 'Score Distribution':
                ticks.append([])
            if xy[0] == PLOT[0] - 10:
                ticks[-1].append(text)
            return original(draw, xy, text, *args, **kwargs)
        with patch.object(ImageDraw.ImageDraw, 'text', record):
            render_distribution(scores)
        self.assertEqual(ticks, [['0', '26', '52', '78', '104', '130']] * 4)

    def test_rare_scores_remain_visible_with_large_all_run_counts(self):
        scores = {number: 0 for number in range(1, 1001)}
        scores[1001] = 100
        gif = Image.open(BytesIO(render_distribution(scores)))
        gif.seek(gif.n_frames - 1)
        image = gif.convert('RGB')
        x = int(PLOT[0] + 100.5 * (PLOT[2] - PLOT[0]) / 101)
        self.assertEqual(image.getpixel((x, PLOT[3] - 1)), (76, 155, 232))

    def test_interface_orders_ids_and_closes_connection(self):
        from ax3l.interface.SnakeLab import SnakeLab
        with patch('ax3l.interface.SnakeLab.DbMgr') as db_class:
            db = db_class.return_value
            db.query.return_value = [dict(id=1, high_score=None), dict(id=3, high_score=0),
                                     dict(id=4, high_score=20)]
            self.assertEqual(SnakeLab().get_run_scores(), {1: None, 3: 0, 4: 20})
            db.query.assert_called_once_with('SELECT id, high_score FROM simulation_runs ORDER BY id')
            self.assertFalse(db_class.call_args.kwargs['initialize_event_tables'])
            db.close.assert_called_once()
            db.close.reset_mock()
            db.query.side_effect = RuntimeError('offline')
            with self.assertRaises(RuntimeError):
                SnakeLab().get_run_scores()
            db.close.assert_called_once()

    def test_http_page_snapshot_empty_and_failure(self):
        from base64 import b64decode
        import re
        from threading import Thread
        from urllib.error import HTTPError
        from urllib.request import urlopen
        from ax3l.server.ReportingServer import make_server
        snake = self.enterContext(patch('ax3l.server.ReportingServer.SnakeLab')).return_value
        server = make_server('127.0.0.1', 0)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f'http://127.0.0.1:{server.server_port}/score-distribution'
            snake.get_run_scores.return_value = {1: 0, 2: 4, 3: 9, 4: None}
            with urlopen(url) as response:
                page = response.read().decode()
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertIn('All simulations: 4 (3 scored).', page)
            self.assertNotIn('Plotly', page)
            self.assertNotIn('<script', page)
            self.assertIn('Back to event log', page)
            encoded = re.search(r'data:image/gif;base64,([^" ]+)', page)[1]
            gif = Image.open(BytesIO(b64decode(encoded)))
            self.assertEqual(gif.n_frames, 2)
            snake.get_run_scores.assert_called_once()
            snake.get_run_scores.return_value = {}
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
