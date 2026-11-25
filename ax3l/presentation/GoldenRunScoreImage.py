"""Render the golden run's training score percentiles as an embedded PNG."""

from base64 import b64encode
from io import BytesIO
from math import ceil, floor, log10

from PIL import Image, ImageDraw, ImageFont

from ax3l.activity.ScorePercentiles import score_percentiles


def golden_run_score_image(episodes: list[dict]) -> str:
    points = score_percentiles(episodes)
    background, foreground, muted = "#101720", "#eef3fb", "#b8c8d8"
    image = Image.new("RGB", (1056, 768), background)
    draw = ImageDraw.Draw(image)
    fonts = {size: ImageFont.load_default(size=size) for size in (16, 18, 24, 40)}
    draw.text((118, 20), "Golden run score", font=fonts[40], fill=foreground)
    draw.text((118, 72), "Percentiles per 50-epoch window (final window may be shorter)",
              font=fonts[16], fill=muted)

    # Round the spacing down so even small score ranges have five interior guides.
    maximum = max((point["p90"] for point in points), default=0)
    target = max(1, maximum) / 6
    unit = 10 ** floor(log10(target))
    step = max(value for value in (1, 2, 2.5, 5) if value <= target / unit) * unit
    intervals = max(6, ceil(maximum / step))
    ceiling = intervals * step
    last_epoch = max((point["epoch"] for point in points), default=1)
    epoch_step = max(1, ceil(last_epoch / 5))
    epoch_ticks = list(range(0, last_epoch, epoch_step)) + [last_epoch]
    left, right = 118, 1004

    for field, title, color, top, bottom in (
        ("p90", "90th percentile", "#4db3ff", 150, 366),
        ("p25", "25th percentile", "#ffbd70", 454, 670),
    ):
        draw.text((left, top - 36), title, font=fonts[24], fill=foreground)
        for tick in range(intervals + 1):
            value = tick * step
            y = bottom - (bottom - top) * value / ceiling
            draw.line((left, y, right, y), fill="#35495e")
            draw.text((left - 12, y), f"{value:g}", anchor="rm", font=fonts[16], fill=muted)
        for epoch in epoch_ticks:
            x = left + (right - left) * epoch / last_epoch
            for y in range(top, bottom, 7):
                draw.line((x, y, x, min(y + 2, bottom)), fill="#516b83")
            if field == "p25":
                draw.text((x, bottom + 22), f"{epoch:,.0f}", anchor="mm", font=fonts[16], fill=muted)
        draw.line((left, top, left, bottom, right, bottom), fill="#62758a")
        label = Image.new("RGBA", (100, 30))
        ImageDraw.Draw(label).text((50, 15), "Score", anchor="mm", font=fonts[18], fill=foreground)
        label = label.rotate(90, expand=True)
        image.paste(label, (42, (top + bottom - label.height) // 2), label)
        coordinates = [(left + (right - left) * point["epoch"] / last_epoch,
                        bottom - (bottom - top) * point[field] / ceiling) for point in points]
        if len(coordinates) > 1:
            draw.line(coordinates, fill=color, width=4)
        for x, y in coordinates:
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=color)
        if not points:
            draw.text(((left + right) / 2, (top + bottom) / 2), "No recorded episode scores",
                      anchor="mm", font=fonts[24], fill=foreground)
    draw.text(((left + right) / 2, 728), "Training epoch", anchor="mm", font=fonts[18], fill=foreground)
    output = BytesIO()
    image.save(output, format="PNG")
    return "data:image/png;base64," + b64encode(output.getvalue()).decode("ascii")
