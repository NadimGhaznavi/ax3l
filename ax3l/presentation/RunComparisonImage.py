"""Render recorded golden/latest training progress comparisons."""

from base64 import b64encode
from io import BytesIO
from math import ceil, floor, hypot, log10

from PIL import Image, ImageDraw, ImageFont

from ax3l.activity.ExplorationProgress import exploration_progress
from ax3l.activity.RewardProgress import reward_progress
from ax3l.activity.ScorePercentiles import score_percentiles
from ax3l.activity.TrainingProgress import training_progress
from ax3l.entities.ExperimentView import ExperimentView


GOLDEN = "#ffbd70"
LATEST = "#4db3ff"
FOREGROUND = "#eef3fb"
MUTED = "#b8c8d8"


def run_comparison_image(view: ExperimentView, reference_episodes: list[dict],
                         latest_episodes: list[dict]) -> str:
    exploration = view.name == "exploration"
    rewards = view.name == "reward-signals"
    training = view.name == "training"
    window_size = 50 if view.name == "architecture" else 150
    runs = [("Golden", GOLDEN, reference_episodes), ("Latest", LATEST, latest_episodes)]
    scores = [(color, score_percentiles(episodes, window_size)) for _, color, episodes in runs]
    height = {"architecture": 768, "exploration": 1000, "reward-signals": 1254, "training": 768}[view.name]
    image = Image.new("RGB", (1056, height), "#101720")
    draw = ImageDraw.Draw(image)
    fonts = {size: ImageFont.load_default(size=size) for size in (16, 18, 24, 40)}
    title = ("Training performance comparison" if training else "Reward signals comparison"
             if rewards else f"{view.name.title()} run comparison")
    draw.text((118, 20), title, font=fonts[40], fill=FOREGROUND)
    draw.text((118, 74), f"Recorded results per {window_size}-epoch window (final window may be shorter)",
              font=fonts[16], fill=MUTED)
    for name, color, x in (("Golden", GOLDEN, 770), ("Latest", LATEST, 902)):
        draw.line((x, 112, x + 32, 112), fill=color, width=4)
        draw.text((x + 42, 112), name, anchor="lm", font=fonts[18], fill=FOREGROUND)

    last_epoch = max((point["epoch"] for _, points in scores for point in points), default=1)
    maximum = max((point["p90"] for _, points in scores for point in points), default=0)
    ceiling, step = _axis(maximum)

    panels = []
    if exploration:
        series = []
        for _, color, episodes in runs:
            points = exploration_progress(episodes, window_size)
            end = next((index + 1 for index, point in enumerate(points) if point["epsilon"] == 0), len(points))
            series.append((color, [(point["epoch"], point["epsilon"]) for point in points[:end]], False))
            series.append((color, [(point["epoch"], point["epsilon_nice_rate"])
                                   for point in points if point["post_epsilon"]], True))
        panels.append(("Exploration", "", 1, .25, series))
    if rewards:
        rates = [(color, reward_progress(episodes, window_size)) for _, color, episodes in runs]
        rate_maximum = max((point[field] for _, points in rates for point in points
                            for field in ("food", "wall", "snake") if point[field] is not None), default=0)
        rate_ceiling, rate_step = _axis(rate_maximum)
        for field, title in (("food", "Food collected"), ("wall", "Wall collisions"), ("snake", "Snake collisions")):
            series = [(color, [(point["epoch"], point[field]) for point in points], False)
                      for color, points in rates]
            panels.append((title, "Per 100 moves", rate_ceiling, rate_step, series))
    if rewards or training:
        series = [(color, [(point["epoch"], point[field]) for point in points], field == "p25")
                  for color, points in scores for field in ("p90", "p25")]
        panels.append(("Score percentiles", "Score", ceiling, step, series))
        if training:
            losses = [(color, training_progress(episodes, window_size)) for _, color, episodes in runs]
            loss_maximum = max((point["loss"] for _, points in losses for point in points
                                if point["loss"] is not None), default=0)
            loss_ceiling, loss_step = _axis(loss_maximum)
            series = [(color, [(point["epoch"], point["loss"]) for point in points], False)
                      for color, points in losses]
            panels.append(("Training loss", "Mean loss", loss_ceiling, loss_step, series))
    else:
        for field, title in (("p90", "90th percentile"), ("p25", "25th percentile")):
            series = [(color, [(point["epoch"], point[field]) for point in points], False)
                      for color, points in scores]
            panels.append((title, "Score", ceiling, step, series))

    for index, (title, label, limit, spacing, series) in enumerate(panels):
        top = 178 + index * (254 if len(panels) > 2 else 274)
        bottom = top + (170 if len(panels) > 2 else 200)
        draw.text((118, top - 36), title, font=fonts[24], fill=FOREGROUND)
        if exploration and index == 0:
            _line_styles(draw, fonts, top, "Epsilon probability", "Moves overridden by EpsilonNice")
        if (rewards and index == 3) or (training and index == 0):
            _line_styles(draw, fonts, top, "90th percentile", "25th percentile")
        _panel(image, draw, fonts, top, bottom, last_epoch, limit, spacing, label,
               series, percent=exploration and index == 0, epoch_labels=index == len(panels) - 1)
        missing = [name for name, _, episodes in runs if not episodes]
        if missing:
            draw.text((561, (top + bottom) / 2), "No recorded episodes: " + ", ".join(missing),
                      anchor="mm", font=fonts[24], fill=FOREGROUND)
        elif rewards and index < 3:
            field = ("food", "wall", "snake")[index]
            unavailable = [name for (name, _, _), (_, points) in zip(runs, rates)
                           if any(point[field] is None for point in points)]
            if unavailable:
                draw.text((1004, bottom + 8), "Gaps: " + ", ".join(unavailable) + " rates unavailable",
                          anchor="rt", font=fonts[16], fill=MUTED)
        elif training and index == 1:
            unavailable = [name for (name, _, _), (_, points) in zip(runs, losses)
                           if any(point["loss"] is None for point in points)]
            if unavailable:
                draw.text((1004, top - 22), "Gaps: " + ", ".join(unavailable) + " loss unavailable",
                          anchor="rm", font=fonts[16], fill=MUTED)

    draw.text((561, height - 72), "Training epoch", anchor="mm", font=fonts[18], fill=FOREGROUND)
    note = ("Each point summarizes the preceding 150 epochs; mean loss excludes missing values."
            if training else "Each point summarizes the preceding 150 epochs; rates = total events / total moves x 100."
            if rewards else "Epsilon is sampled at checkpoints; overrides = total EpsilonNice moves / total moves in each window."
            if exploration else "Score percentiles summarize each run independently on shared epoch and score axes.")
    draw.text((118, height - 36), note, font=fonts[16], fill=MUTED)
    output = BytesIO()
    image.save(output, format="PNG")
    return "data:image/png;base64," + b64encode(output.getvalue()).decode("ascii")


def _axis(maximum: float) -> tuple[float, float]:
    target = max(1, maximum) / 6
    unit = 10 ** floor(log10(target))
    step = max(value for value in (1, 2, 2.5, 5) if value <= target / unit) * unit
    return max(6, ceil(maximum / step)) * step, step


def _line_styles(draw, fonts, top, solid, dashed):
    draw.line((354, top - 22, 390, top - 22), fill=MUTED, width=3)
    draw.text((400, top - 22), solid, anchor="lm", font=fonts[16], fill=MUTED)
    _dashed_line(draw, (626, top - 22), (662, top - 22), MUTED)
    draw.text((672, top - 22), dashed, anchor="lm", font=fonts[16], fill=MUTED)


def _panel(image, draw, fonts, top, bottom, last_epoch, ceiling, step, label, series, *, percent, epoch_labels):
    left, right = 118, 1004
    for tick in range(round(ceiling / step) + 1):
        value = tick * step
        y = bottom - (bottom - top) * value / ceiling
        draw.line((left, y, right, y), fill="#35495e")
        text = f"{value:.0%}" if percent else f"{value:g}"
        draw.text((left - 12, y), text, anchor="rm", font=fonts[16], fill=MUTED)
    epoch_step = max(1, ceil(last_epoch / 5))
    for epoch in list(range(0, last_epoch, epoch_step)) + [last_epoch]:
        x = left + (right - left) * epoch / last_epoch
        for y in range(top, bottom, 7):
            draw.line((x, y, x, min(y + 2, bottom)), fill="#516b83")
        if epoch_labels:
            draw.text((x, bottom + 22), f"{epoch:,}", anchor="mm", font=fonts[16], fill=MUTED)
    draw.line((left, top, left, bottom, right, bottom), fill="#62758a")
    if label:
        label_width = ceil(draw.textlength(label, font=fonts[18])) + 8
        axis = Image.new("RGBA", (label_width, 30))
        ImageDraw.Draw(axis).text((label_width / 2, 15), label, anchor="mm", font=fonts[18], fill=FOREGROUND)
        axis = axis.rotate(90, expand=True)
        image.paste(axis, (42, (top + bottom - axis.height) // 2), axis)
    for color, points, dashed in series:
        previous = None
        for epoch, value in points:
            if value is None:
                previous = None
                continue
            x = left + (right - left) * epoch / last_epoch
            y = bottom - (bottom - top) * value / ceiling
            if previous is not None:
                if dashed:
                    _dashed_line(draw, previous, (x, y), color)
                else:
                    draw.line((*previous, x, y), fill=color, width=4)
            if dashed:
                draw.rectangle((x - 3, y - 3, x + 3, y + 3), fill=color)
            else:
                draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=color)
            previous = x, y


def _dashed_line(draw, start, end, color):
    length = hypot(end[0] - start[0], end[1] - start[1])
    if length == 0:
        return
    for offset in range(0, ceil(length), 20):
        first, last = offset / length, min(offset + 12, length) / length
        draw.line((start[0] + (end[0] - start[0]) * first, start[1] + (end[1] - start[1]) * first,
                   start[0] + (end[0] - start[0]) * last, start[1] + (end[1] - start[1]) * last),
                  fill=color, width=3)
