"""Render successive 200-simulation distributions on a fixed all-run scale."""

from base64 import b64encode
from collections import Counter
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


BLOCK_SIZE = 200
FONT = Path(__file__).parent / 'fonts' / 'DejaVuSansMono.ttf'
SIZE = (800, 480)
PLOT = (90, 110, 775, 350)


def distribution_frames(scores: dict[int, int | None]) -> list[tuple[str, list[int | None]]]:
    """Use complete ID blocks; null scores occupy a slot but contribute no bar."""
    rows = sorted(scores.items())
    groups = {}
    for run_id, score in rows:
        groups.setdefault((run_id - 1) // BLOCK_SIZE, []).append(score)
    frames = [('Before simulation #1', [])]
    for block, values in sorted(groups.items()):
        if len(values) == BLOCK_SIZE:
            first = block * BLOCK_SIZE + 1
            frames.append((f'Simulations #{first}–{first + BLOCK_SIZE - 1}', values))
    label = f'All simulations #{rows[0][0]}–{rows[-1][0]}' if rows else 'All simulations'
    frames.append((label, [score for _, score in rows]))
    return frames


def render_distribution(scores: dict[int, int | None]) -> bytes:
    """Render latest validated scores; the final distribution defines both axes."""
    frames = distribution_frames(scores)
    all_counts = Counter(score for score in scores.values() if score is not None)
    low, high = min(all_counts, default=0), max(all_counts, default=0)
    y_step = max(1, (max(all_counts.values(), default=0) + 4) // 5)
    ceiling = y_step * 5
    x_step = max(1, (high - low + 5) // 6)
    fonts = {size: ImageFont.truetype(str(FONT), size) for size in (18, 20, 24, 28)}
    left, top, right, bottom = PLOT
    bin_width = (right - left) / (high - low + 1)

    def x_position(score):
        return left + (score - low + .5) * bin_width

    images = []
    for label, values in frames:
        image = Image.new('RGB', SIZE, '#101720')
        draw = ImageDraw.Draw(image)
        draw.text((24, 16), 'Score Distribution', font=fonts[28], fill='#d5dfeb')
        draw.text((24, 56), label, font=fonts[24], fill='#d5dfeb')
        draw.rectangle(PLOT, fill='#151f2b')
        for tick in range(6):
            value = tick * y_step
            y = bottom - (bottom - top) * value / ceiling
            draw.line((left, y, right, y), fill='#40566e')
            draw.text((left - 10, y), f'{value:,}', anchor='rm', font=fonts[18], fill='#a7b8cb')
        ticks = list(range(low, high + 1, x_step))
        if ticks[-1] != high and (high - ticks[-1]) >= x_step / 2:
            ticks.append(high)
        for value in ticks:
            x = x_position(value)
            draw.line((x, top, x, bottom), fill='#40566e')
            draw.text((x, bottom + 20), str(value), anchor='mm', font=fonts[18], fill='#a7b8cb')
        counts = Counter(score for score in values if score is not None)
        for score, count in sorted(counts.items()):
            x = x_position(score)
            y = min(bottom - 1, bottom - (bottom - top) * count / ceiling)
            half_width = bin_width * .92 / 2
            border = min(4, int(half_width / 2), int((bottom - y) / 3))
            draw.rectangle((x - half_width, y, x + half_width, bottom - 1),
                           fill='#4c9be8', outline='#101923', width=border)
        draw.line((left, top, left, bottom), fill='#a7b8cb')
        draw.line((left, bottom, right, bottom), fill='#a7b8cb')
        draw.text(((left + right) / 2, 410), 'Run high score', anchor='mm',
                  font=fonts[24], fill='#d5dfeb')
        # Rotate a transparent label to keep the histogram's vertical Y title.
        axis = Image.new('RGBA', (220, 28))
        ImageDraw.Draw(axis).text((110, 14), 'Number of runs', anchor='mm',
                                 font=fonts[20], fill='#d5dfeb')
        axis = axis.rotate(90, expand=True)
        image.paste(axis, (8, 120), axis)
        draw.text((24, 450), f'{len(values):,} submitted · {sum(counts.values()):,} scored',
                  font=fonts[20], fill='#a7b8cb')
        images.append(image)
    # Share one palette so fixed axes and text retain identical colours in every frame.
    palette = images[-1].quantize(colors=256)
    images = [image.quantize(palette=palette, dither=Image.Dither.NONE) for image in images]
    output = BytesIO()
    images[0].save(output, format='GIF', save_all=True, append_images=images[1:],
                   duration=[2000] * (len(images) - 1) + [5000], loop=0, disposal=2)
    return output.getvalue()


def distribution(scores: dict[int, int | None]) -> dict:
    """Keep the animation and page counts in the same database snapshot."""
    return dict(total=len(scores), scored=sum(score is not None for score in scores.values()),
                animation=b64encode(render_distribution(scores)).decode('ascii'))
