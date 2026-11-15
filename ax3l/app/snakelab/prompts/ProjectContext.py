from ax3l.app.Prompt import Prompt


class ProjectContext(Prompt):
    def __init__(self):
        super().__init__(
            "Improve Snake Lab high scores over 500 episodes. Complete your assigned choice, then stop. "
            "data_tool reads experiment data; kb_tool reads guides (/selection or /). "
            "Read only what you need."
        )
