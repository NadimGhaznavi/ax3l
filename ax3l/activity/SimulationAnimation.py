"""Render validated Snake Lab game frames as a looping GIF."""

from io import BytesIO
from collections.abc import Iterator

from PIL import Image, ImageDraw


class SimulationAnimation:
    VERSION = 5
    FINAL_FRAME_DURATION_MS = 1000
    FOOD_FRAME_DURATION_MS = 50
    CELL_SIZE = 32
    COLOURS = ("#101720", "#23364b", "#4c9be8", "#79b8f3", "#f09445", "#b8682f")

    @classmethod
    def render(cls, frames: list[dict], duration_ms: int = 75) -> bytes:
        """Digest food to the visible tail, revealing growth on the next move."""
        images = cls._gif_timing(cls._images(frames, duration_ms))
        first = next(images)
        with BytesIO() as output:
            first.save(output, format="GIF", save_all=True, append_images=images,
                       loop=0, disposal=1, optimize=False)
            return output.getvalue()

    @staticmethod
    def _gif_timing(images: Iterator[Image.Image]) -> Iterator[Image.Image]:
        """Round cumulative time to GIF ticks without accumulating timing drift."""
        elapsed_ms = encoded_ms = 0
        for image in images:
            elapsed_ms += image.info["duration"]
            next_ms = ((elapsed_ms + 5) // 10) * 10
            image.info["duration"] = next_ms - encoded_ms
            encoded_ms = next_ms
            yield image

    @classmethod
    def _images(cls, frames: list[dict], duration_ms: int) -> Iterator[Image.Image]:
        previous = None
        digestion_head = None
        for index, frame in enumerate(frames):
            board = frame["board"]
            if board["snake_head"] != digestion_head:
                digestion_head = None
            if (previous is not None and board["score"] > previous["score"]
                    and board["snake_head"] == previous["food"]):
                # Move onto the food at the old length, delaying growth and new food.
                eating = {**board, "snake_body": board["snake_body"][:-1],
                          "food": None, "score": previous["score"]}
                for segment in range(1 + len(eating["snake_body"])):
                    image = cls._board(eating, segment)
                    image.info["duration"] = cls.FOOD_FRAME_DURATION_MS
                    yield image
                digestion_head = board["snake_head"]
                previous = board
                if index != len(frames) - 1:
                    continue
            if digestion_head is not None:
                # Keep the old length until a captured move advances the head.
                board = {**board, "snake_body": board["snake_body"][:-1]}
            image = cls._board(board)
            image.info["duration"] = (
                cls.FINAL_FRAME_DURATION_MS if index == len(frames) - 1 else duration_ms
            )
            yield image
            previous = frame["board"]

    @classmethod
    def _board(cls, board: dict, food_segment: int | None = None) -> Image.Image:
        cell = cls.CELL_SIZE
        width, height = board["grid_size"]
        image = Image.new("P", (width * cell, height * cell), 0)
        palette = [int(colour[offset:offset + 2], 16)
                   for colour in cls.COLOURS for offset in (1, 3, 5)]
        image.putpalette(palette + [0] * (768 - len(palette)))
        draw = ImageDraw.Draw(image)
        for x in range(width + 1):
            draw.line((x * cell, 0, x * cell, height * cell), fill=1)
        for y in range(height + 1):
            draw.line((0, y * cell, width * cell, y * cell), fill=1)
        for segment, (x, y) in enumerate(board["snake_body"], start=1):
            draw.rounded_rectangle((x * cell + 2, y * cell + 2,
                                    (x + 1) * cell - 3, (y + 1) * cell - 3),
                                   radius=5, fill=5 if segment == food_segment else 2)
        x, y = board["snake_head"]
        draw.rounded_rectangle((x * cell + 1, y * cell + 1,
                                (x + 1) * cell - 2, (y + 1) * cell - 2),
                               radius=6, fill=5 if food_segment == 0 else 3)
        if board["food"] is not None:
            x, y = board["food"]
            cx, cy, radius = (x + .5) * cell, (y + .5) * cell, cell * .3
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=4)
        return image
