from ax3l.app.Prompt import Prompt


class ProjectContext(Prompt):
    def __init__(self):
        super().__init__(
            "Ax3l optimizes high scores in Snake Lab 3.0.1. Each simulation trains a "
            "Transformer with four attention heads for 500 episodes. Its 24-value "
            "feature vector contains body danger left/straight/right (0-2), wall "
            "danger left/straight/right (3-5), heading left/right/up/down (6-9), food "
            "direction left/right/up/down (10-13), food alignment on X/Y (14-15), "
            "seven big-endian length bits saturating at 127 (16-22), and remaining "
            "move-budget fraction (23). It has no full-board view or food-distance "
            "measurement. Actions are left, straight, and right relative to heading. "
            "Distance shaping uses Manhattan progress. EpsilonNice is required and "
            "its probability and duration are tunable after ordinary epsilon ends. "
            "Nice safety covers immediate collisions; detours can still enter traps. "
            "Propose only the assigned parameter or pair to improve the high score."
        )
