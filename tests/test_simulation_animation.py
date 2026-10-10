"""Verify game playback, ZMQ retrieval, atomic caching, and report delivery."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen
from uuid import uuid4

from PIL import Image, ImageSequence
import zmq

from ax3l.activity.SimulationAnimation import SimulationAnimation
from ax3l.interface.SimulationGifStore import SimulationGifStore
from ax3l.interface.SnakeLab import SnakeLab, SnakeLabQueryError
from ax3l.server.ReportingServer import make_server


def game_frames():
    board = dict(grid_size=[4, 3], snake_head=[1, 1], snake_body=[[0, 1]],
                 food=[3, 1], direction=[1, 0], score=0)
    frames = [dict(version=1, episode=2, step=0, board=board)]
    frames.append(dict(version=1, episode=2, step=1,
                       board={**board, 'snake_head': [2, 1], 'snake_body': [[1, 1]]}))
    frames.append(dict(version=1, episode=2, step=2,
                       board={**board, 'snake_head': [3, 1],
                              'snake_body': [[2, 1], [1, 1]], 'food': None, 'score': 1}))
    frames.append({**deepcopy(frames[-1]), 'step': 3})  # Collision keeps the board.
    return frames


class SimulationAnimationTests(unittest.TestCase):
    def test_playback_colours_timing_and_terminal_board(self):
        data = SimulationAnimation.render(game_frames())
        with Image.open(BytesIO(data)) as gif:
            self.assertEqual(gif.size, (128, 96))
            self.assertEqual(gif.info['loop'], 0)
            durations = []
            heads = []
            for frame in ImageSequence.Iterator(gif):
                durations.append(frame.info['duration'])
                pixels = frame.convert('RGB')
                heads.append([pixels.getpixel((x * 32 + 16, 48)) for x in (1, 2, 3)])
            # Identical penultimate and terminal boards share their elapsed time.
            self.assertEqual(durations, [80, 70, 50, 50, 1080])
            self.assertEqual(sum(durations), 1330)
            for colours, head in ((heads[0], 0), (heads[1], 1), (heads[-1], 2)):
                self.assertEqual(colours[head], (121, 184, 243))
            self.assertEqual(heads[-1][1], (76, 155, 232))
            self.assertEqual(pixels.getpixel((0, 0)), (35, 54, 75))

    def test_single_frame(self):
        with Image.open(BytesIO(SimulationAnimation.render(game_frames()[:1]))) as gif:
            self.assertEqual(gif.n_frames, 1)
            self.assertEqual(gif.info['duration'], 1000)

    def test_distinct_final_frame_pauses_for_one_second(self):
        with Image.open(BytesIO(SimulationAnimation.render(game_frames()[:3]))) as gif:
            self.assertEqual(gif.info['loop'], 0)
            self.assertEqual([frame.info['duration'] for frame in ImageSequence.Iterator(gif)],
                             [80, 70, 50, 50, 1000])

    def test_custom_move_duration_keeps_final_pause(self):
        with Image.open(BytesIO(SimulationAnimation.render(game_frames()[:3], 120))) as gif:
            self.assertEqual([frame.info['duration'] for frame in ImageSequence.Iterator(gif)],
                             [120, 120, 50, 50, 1000])

    def test_move_rounding_preserves_average_without_drift(self):
        frames = [deepcopy(game_frames()[index % 2]) for index in range(21)]
        with Image.open(BytesIO(SimulationAnimation.render(frames))) as gif:
            durations = [frame.info['duration'] for frame in ImageSequence.Iterator(gif)]
        self.assertEqual(durations, [80, 70] * 10 + [1000])
        self.assertEqual(sum(durations), 20 * 75 + 1000)

    def test_food_travels_along_frozen_length_five_snake_before_growth(self):
        before = dict(grid_size=[8, 4], snake_head=[4, 1],
                      snake_body=[[3, 1], [3, 2], [2, 2], [1, 2]],
                      food=[5, 1], direction=[1, 0], score=0)
        after = {**before, 'snake_head': [5, 1],
                 'snake_body': [[4, 1], *before['snake_body']], 'food': [6, 3], 'score': 1}
        frames = [dict(board=before), dict(board=after)]
        original = deepcopy(frames)
        with Image.open(BytesIO(SimulationAnimation.render(frames))) as gif:
            self.assertEqual(gif.info['loop'], 0)
            playback = [(image.convert('RGB'), image.info['duration'])
                        for image in ImageSequence.Iterator(gif)]
        self.assertEqual([duration for _, duration in playback], [80, *([50] * 5), 1000])
        frozen_snake = [[5, 1], [4, 1], [3, 1], [3, 2], [2, 2]]

        def colour(image, position):
            x, y = position
            return image.getpixel((x * 32 + 16, y * 32 + 16))

        for travelling_segment, (image, _) in enumerate(playback[1:-1]):
            for segment, position in enumerate(frozen_snake):
                expected = ((184, 104, 47) if segment == travelling_segment
                            else (121, 184, 243) if segment == 0 else (76, 155, 232))
                self.assertEqual(colour(image, position), expected)
            # No growth or replacement food appears until the mini animation ends.
            self.assertEqual(colour(image, [1, 2]), (16, 23, 32))
            self.assertEqual(colour(image, [6, 3]), (16, 23, 32))
        final, _ = playback[-1]
        self.assertEqual(colour(final, [5, 1]), (121, 184, 243))
        for position in after['snake_body']:
            self.assertEqual(colour(final, position), (76, 155, 232))
        self.assertEqual(colour(final, [6, 3]), (240, 148, 69))
        self.assertEqual(frames, original)

    def test_moves_without_food_do_not_insert_animation(self):
        with Image.open(BytesIO(SimulationAnimation.render(game_frames()[:2]))) as gif:
            self.assertEqual([frame.info['duration'] for frame in ImageSequence.Iterator(gif)],
                             [80, 1000])

    def test_consecutive_pickups_each_animate_their_own_snake_length(self):
        first = dict(grid_size=[5, 2], snake_head=[1, 0], snake_body=[[0, 0]],
                     food=[2, 0], score=0, direction=[1, 0])
        second = {**first, 'snake_head': [2, 0], 'snake_body': [[1, 0], [0, 0]],
                  'food': [3, 0], 'score': 1}
        third = {**first, 'snake_head': [3, 0], 'snake_body': [[2, 0], [1, 0], [0, 0]],
                 'food': None, 'score': 2}
        with Image.open(BytesIO(SimulationAnimation.render([dict(board=board)
                                                           for board in (first, second, third)]))) as gif:
            self.assertEqual([frame.info['duration'] for frame in ImageSequence.Iterator(gif)],
                             [80, 50, 50, 70, 50, 50, 50, 1000])

    def test_atomic_write_and_failure_cleanup(self):
        with TemporaryDirectory() as directory:
            store = SimulationGifStore(Path(directory), 1, 100)
            run_id = str(uuid4())
            path = store.save(run_id, b'original')
            with patch.object(Path, 'replace', side_effect=OSError('write failure')):
                with self.assertRaisesRegex(OSError, 'write failure'):
                    store.save(run_id, b'replacement')
            self.assertEqual(path.read_bytes(), b'original')
            self.assertEqual(list(store.directory.iterdir()), [path])
            self.assertNotEqual(store.path(run_id), SimulationGifStore(Path(directory), 2, 100).path(run_id))
            self.assertNotEqual(store.path(run_id), SimulationGifStore(Path(directory), 1, 200).path(run_id))
            with self.assertRaises(ValueError):
                store.path('../../other')


class HighscoreFramesTests(unittest.TestCase):
    def test_real_zmq_request(self):
        run_id = str(uuid4())
        with zmq.Context() as context, context.socket(zmq.REP) as server:
            server.setsockopt(zmq.RCVTIMEO, 2000)
            port = server.bind_to_random_port('tcp://127.0.0.1')
            with ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(SnakeLab(f'tcp://127.0.0.1:{port}').get_highscore_frames, run_id)
                request = server.recv_json()
                self.assertEqual(request['method'], 'simulation.highscore_frames')
                self.assertEqual(request['payload'], {'run_id': run_id})
                server.send_json(dict(protocol_version=1, request_id=request['request_id'],
                                      status='ok', payload=dict(run_id=run_id, frames=game_frames())))
                self.assertEqual(result.result(timeout=2), game_frames())

    def test_missing_capture_and_other_errors(self):
        snake = SnakeLab()
        for code in ('frames_unavailable', 'run_not_found', 'unknown_method'):
            with patch.object(snake, '_request', side_effect=SnakeLabQueryError({'code': code})):
                if code == 'frames_unavailable':
                    self.assertIsNone(snake.get_highscore_frames(str(uuid4())))
                else:
                    with self.assertRaises(SnakeLabQueryError):
                        snake.get_highscore_frames(str(uuid4()))

    def test_reject_invalid_frames_at_protocol_boundary(self):
        run_id = str(uuid4())
        payloads = [{'run_id': run_id, 'frames': []}, {'run_id': 'wrong', 'frames': game_frames()}]
        for key, value in (('step', 7), ('version', True), ('episode', 3)):
            frames = game_frames()
            frames[1][key] = value
            payloads.append(dict(run_id=run_id, frames=frames))
        for key, value in (('snake_head', [-1, 0]), ('grid_size', [4, True]),
                           ('snake_body', None), ('food', [4, 0]), ('score', -1),
                           ('direction', [0, 0])):
            frames = game_frames()
            frames[1]['board'][key] = value
            payloads.append(dict(run_id=run_id, frames=frames))
        snake = SnakeLab()
        for payload in payloads:
            with self.subTest(payload=payload), patch.object(snake, '_request', return_value=payload):
                with self.assertRaises(ValueError):
                    snake.get_highscore_frames(run_id)


class AnimationReportTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(TemporaryDirectory())
        self.run_id = str(uuid4())
        self.enterContext(patch('ax3l.server.ReportingServer.DbMgr'))
        self.log = self.enterContext(patch('ax3l.server.ReportingServer.EventLogDb')).return_value
        self.log.recent.return_value = []
        self.log.current_golden_config.return_value = {'process_id': self.run_id}
        self.log.experiment_cycles.return_value = 1
        self.snake = self.enterContext(patch('ax3l.server.ReportingServer.SnakeLab')).return_value
        self.enterContext(patch('ax3l.app.ReportBackground.SnakeLab', return_value=self.snake))
        self.enterContext(patch('ax3l.app.ReportBackground.DbMgr'))
        self.enterContext(patch('ax3l.app.ReportBackground.EventLogDb', return_value=self.log))
        self.snake.get_run_summary.return_value = dict(run_id=self.run_id, high_score=1,
            project_version='2.0.0', completed_at=None, high_score_snapshot=game_frames()[-1])
        self.snake.get_highscore_frames.return_value = game_frames()
        self.snake.get_high_score.return_value = 1
        self.snake.get_num_sims.return_value = 1
        self.snake.get_episode_totals.return_value = dict(games_played=2, moves_made=4)
        self.server = make_server('127.0.0.1', 0, Path(self.directory))
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join)
        self.addCleanup(self.server.shutdown)
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.gif_url = f'/simulation-gifs/v4-75ms/{self.run_id}.gif'

    def page(self, path):
        with urlopen(self.base + path) as response:
            return response.read().decode()

    def test_both_reports_cache_and_serve_gif_after_restart(self):
        published = Event()
        save = SimulationGifStore.save

        def publish(store, run_id, animation):
            path = save(store, run_id, animation)
            published.set()
            return path

        with patch.object(SimulationGifStore, 'save', publish):
            self.page('/')
            self.assertTrue(published.wait(3), 'Background GIF was not saved')
        for path in ('/', f'/simulations/{self.run_id}'):
            page = self.page(path)
            self.assertIn(f'src="{self.gif_url}"', page)
            self.assertNotIn('<svg ', page)
        self.snake.get_highscore_frames.assert_called_once_with(self.run_id)
        with urlopen(self.base + self.gif_url) as response:
            self.assertEqual(response.headers['Content-Type'], 'image/gif')
            with Image.open(BytesIO(response.read())) as gif:
                self.assertEqual(gif.size, (128, 96))
                self.assertGreater(gif.n_frames, 1)
                self.assertEqual(gif.info['loop'], 0)
                self.assertEqual([frame.info['duration'] for frame in ImageSequence.Iterator(gif)],
                                 [80, 70, 50, 50, 1080])
        cached = list(Path(self.directory).rglob('*.gif'))
        self.assertEqual(len(cached), 1)
        self.snake.get_highscore_frames.side_effect = AssertionError('Must reuse saved GIF')
        with make_server('127.0.0.1', 0, Path(self.directory)) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urlopen(f'http://127.0.0.1:{server.server_port}/simulations/{self.run_id}') as response:
                    self.assertIn(self.gif_url, response.read().decode())
            finally:
                server.shutdown()
                thread.join()

    def test_unavailable_frames_and_transport_outage_keep_svg(self):
        self.snake.get_highscore_frames.return_value = None
        for failure in (None, zmq.Again()):
            self.snake.get_highscore_frames.side_effect = failure
            for path in ('/', f'/simulations/{self.run_id}'):
                self.assertIn('<svg ', self.page(path))
        self.assertFalse(list(Path(self.directory).rglob('*.gif')))

    def test_slow_gif_and_totals_do_not_block_pages_or_health(self):
        gif_started, totals_started, release = Event(), Event(), Event()
        self.addCleanup(release.set)

        def retrieve(run_id):
            gif_started.set()
            if not release.wait(5):
                raise TimeoutError('Test did not release GIF worker')
            return game_frames()

        def totals():
            totals_started.set()
            if not release.wait(5):
                raise TimeoutError('Test did not release totals worker')
            return dict(games_played=2, moves_made=4)

        self.snake.get_highscore_frames.side_effect = retrieve
        self.snake.get_episode_totals.side_effect = totals
        try:
            # These requests must complete while both workers are still blocked.
            for path in ('/', f'/simulations/{self.run_id}', '/health', '/'):
                with urlopen(self.base + path, timeout=1) as response:
                    page = response.read().decode()
                if path == '/':
                    self.assertIn('Games Played: —', page)
                    self.assertIn('Moves Made: —', page)
                if path != '/health':
                    self.assertIn('<svg ', page)
            self.assertTrue(gif_started.wait(1))
            self.assertTrue(totals_started.wait(1))
            self.snake.get_highscore_frames.assert_called_once_with(self.run_id)
            self.snake.get_episode_totals.assert_called_once_with()
        finally:
            release.set()

    def test_slow_experiment_history_does_not_block_homepage_or_health(self):
        started, release = Event(), Event()
        self.addCleanup(release.set)

        def cycles():
            started.set()
            if not release.wait(5):
                raise TimeoutError('Test did not release experiment history')
            return 100

        self.log.experiment_cycles.side_effect = cycles
        try:
            for path in ('/', '/health', '/'):
                with urlopen(self.base + path, timeout=1) as response:
                    page = response.read().decode()
                if path == '/':
                    self.assertIn('Completed Experiments: —', page)
            self.assertTrue(started.wait(1))
            self.log.experiment_cycles.assert_called_once_with()
        finally:
            release.set()

    def test_missing_files_and_traversal_are_not_served(self):
        for path in (self.gif_url, self.gif_url.replace('v4-', 'v5-'),
                     '/simulation-gifs/../../requirements.txt',
                     f'/simulation-gifs/v4-75ms/{uuid4()}.gif'):
            with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                self.page(path)
            self.assertEqual(error.exception.code, 404)

    def test_invalid_speed_is_rejected(self):
        for duration in (0, -10, 9):
            with self.assertRaises(ValueError):
                make_server('127.0.0.1', 0, Path(self.directory), duration)
