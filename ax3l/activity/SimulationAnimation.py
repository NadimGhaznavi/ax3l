"""Render validated Snake Lab game frames as a looping GIF."""

from io import BytesIO

from PIL import Image, ImageDraw


class SimulationAnimation:
    VERSION = 2
    FINAL_FRAME_DURATION_MS = 1000
    CELL_SIZE = 32
    COLOURS = ("#101720", "#23364b", "#4c9be8", "#79b8f3", "#f09445")

    @classmethod
    def render(cls, frames: list[dict], duration_ms: int = 40) -> bytes:
        """Encode all moves, preserving elapsed time for identical boards."""
        images = (cls._board(frame["board"]) for frame in frames)
        first = next(images)
        durations = [duration_ms] * (len(frames) - 1) + [cls.FINAL_FRAME_DURATION_MS]
        with BytesIO() as output:
            first.save(output, format="GIF", save_all=True, append_images=images,
                       duration=durations, loop=0, disposal=1, optimize=False)
            return output.getvalue()

    @classmethod
    def _board(cls, board: dict) -> Image.Image:
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
        for x, y in board["snake_body"]:
            draw.rounded_rectangle((x * cell + 2, y * cell + 2,
                                    (x + 1) * cell - 3, (y + 1) * cell - 3),
                                   radius=5, fill=2)
        x, y = board["snake_head"]
        draw.rounded_rectangle((x * cell + 1, y * cell + 1,
                                (x + 1) * cell - 2, (y + 1) * cell - 2),
                               radius=6, fill=3)
        if board["food"] is not None:
            x, y = board["food"]
            cx, cy, radius = (x + .5) * cell, (y + .5) * cell, cell * .3
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=4)
        return image
