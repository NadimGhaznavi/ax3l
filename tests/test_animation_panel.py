"""Verify embedded GIF labels, fixed score alignment, borders, and playback."""

from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageSequence

from ax3l.activity.SimulationAnimation import SimulationAnimation


def score_frames(scores):
    return [dict(version=1, step=i, episode=1, board=dict(
        grid_size=[6, 6], snake_head=[i + 1, 1], snake_body=[[i, 1]],
        food=None, direction=[1, 0], score=score)) for i, score in enumerate(scores)]


class AnimationTests(unittest.TestCase):
    def test_embedded_labels_and_padding_on_every_frame(self):
        font_path = Path(__file__).resolve().parents[1] / 'ax3l/activity/fonts/DejaVuSansMono.ttf'
        font = ImageFont.truetype(str(font_path), SimulationAnimation.FONT_SIZE)
        original_text = ImageDraw.ImageDraw.text
        calls = []

        def record(draw, xy, text, *args, **kwargs):
            calls.append((xy, text, kwargs.get('anchor')))
            return original_text(draw, xy, text, *args, **kwargs)

        with patch.object(ImageDraw.ImageDraw, 'text', record):
            data = SimulationAnimation.render(score_frames([9, 10]), simulation_id=123)
        self.assertEqual([call[1] for call in calls], [
            'Simulation #123', 'High Score: 10', 'Current Score:  9',
            'Simulation #123', 'High Score: 10', 'Current Score: 10'])
        self.assertEqual(calls[2][0], calls[5][0])
        self.assertEqual(calls[2][2], 'rt')
        with Image.open(BytesIO(data)) as gif:
            images = [frame.convert('RGB') for frame in ImageSequence.Iterator(gif)]
            self.assertEqual(len(images), 2)
            for image in images:
                self.assertEqual(image.getpixel((0, 0)), (64, 86, 110))
                self.assertEqual(image.getpixel((image.width - 1, image.height - 1)), (64, 86, 110))
            header = (0, 0, gif.width, SimulationAnimation.PANEL_PADDING + SimulationAnimation.HEADER_HEIGHT)
            self.assertIsNone(ImageChops.difference(images[0].crop(header), images[1].crop(header)).getbbox())
            # The footer label's actual raster pixels must stay still at 9 -> 10.
            footer_y = SimulationAnimation.PANEL_PADDING + SimulationAnimation.HEADER_HEIGHT + 6 * 32
            label_right = gif.width - SimulationAnimation.PANEL_PADDING - int(font.getlength('00')) - 1
            footer_label = (0, footer_y, label_right, gif.height)
            self.assertIsNone(ImageChops.difference(images[0].crop(footer_label),
                                                  images[1].crop(footer_label)).getbbox())
            footer = (label_right, footer_y, gif.width, gif.height)
            self.assertIsNotNone(ImageChops.difference(images[0].crop(footer),
                                                     images[1].crop(footer)).getbbox())

    def test_larger_scores_use_a_stable_field_and_keep_all_frames_same_size(self):
        data = SimulationAnimation.render(score_frames([0, 9, 99, 100]), simulation_id=123456789)
        with Image.open(BytesIO(data)) as gif:
            sizes = [frame.size for frame in ImageSequence.Iterator(gif)]
            self.assertTrue(all(size == sizes[0] for size in sizes))
            self.assertEqual(gif.n_frames, 4)
            self.assertEqual(gif.info['loop'], 0)

    def test_digestion_keeps_live_score_and_final_pause(self):
        frames = score_frames([9, 10, 10])
        frames[0]['board']['food'] = frames[1]['board']['snake_head']
        frames[1]['board']['snake_body'] = [[1, 1], [0, 1]]
        frames[2]['board']['snake_body'] = [[2, 1], [1, 1]]
        labels = []
        original_text = ImageDraw.ImageDraw.text

        def record(draw, xy, text, *args, **kwargs):
            if text.startswith('Current Score:'):
                labels.append(text)
            return original_text(draw, xy, text, *args, **kwargs)

        with patch.object(ImageDraw.ImageDraw, 'text', record):
            data = SimulationAnimation.render(frames, simulation_id=42)
        self.assertEqual(labels[0], 'Current Score:  9')
        self.assertTrue(all(label == 'Current Score: 10' for label in labels[1:]))
        self.assertGreater(len(labels), len(frames))
        with Image.open(BytesIO(data)) as gif:
            durations = [frame.info['duration'] for frame in ImageSequence.Iterator(gif)]
            self.assertEqual(durations[-1], 1000)
            self.assertEqual(gif.info['loop'], 0)

    def test_single_frame_game_still_includes_panel_and_pause(self):
        with Image.open(BytesIO(SimulationAnimation.render(score_frames([0]), simulation_id=1))) as gif:
            self.assertEqual(gif.n_frames, 1)
            self.assertEqual(gif.info['duration'], 1000)
            self.assertGreater(gif.width, 6 * 32)
            self.assertGreater(gif.height, 6 * 32)
