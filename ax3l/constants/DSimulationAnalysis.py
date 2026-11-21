"""The ordered, bounded tasks used to interpret a completed simulation."""


class DSimulationAnalysis:
    SECTIONS = {"scores": "Score trends", "distribution": "Score distribution", "loss": "Training loss"}
    CHART_LABELS = {**SECTIONS, "endings": "Game-ending reasons"}
    MAX_WORDS = 40
