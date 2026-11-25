"""Golden/latest placeholders for the reward-signals and training evaluations."""

from base64 import b64encode
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from ax3l.entities.ExperimentView import ExperimentView


def comparison_image(view: ExperimentView, reference_run_id: str, latest_run_id: str) -> str:
    image = Image.new("RGB", (800, 360), "#101720")
    draw = ImageDraw.Draw(image)
    title = ImageFont.load_default(size=28)
    body = ImageFont.load_default(size=18)
    draw.text((32, 32), view.name.replace("-", " ").title(), font=title, fill="#ffffff")
    draw.rectangle((32, 90, 768, 320), outline="#516274", width=2)
    draw.text((56, 116), "Comparison image placeholder", font=title, fill="#ffffff")
    draw.text((56, 174), f"Golden reference: {reference_run_id}", font=body, fill="#b8c8d8")
    draw.text((56, 208), f"Latest simulation: {latest_run_id}", font=body, fill="#b8c8d8")
    draw.text((56, 266), "Results comparison will appear here. No measurements yet.",
              font=body, fill="#b8c8d8")
    output = BytesIO()
    image.save(output, format="PNG")
    return "data:image/png;base64," + b64encode(output.getvalue()).decode("ascii")
