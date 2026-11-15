from ax3l.app.Prompt import Prompt


class ProjectContext(Prompt):
    def __init__(self):
        super().__init__(
            "Ax3l optimizes Snake Lab high scores over 500 episodes. Complete only the assigned task, "
            "call its submission tool, then stop. If reference information is needed, use kb_tool: "
            "/selection explains choices; / links to short guides on models, exploration, and rewards. "
            "Follow only links relevant to your task."
        )
