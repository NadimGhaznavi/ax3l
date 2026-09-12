from ax3l.app.Prompt import Prompt


class Introduction(Prompt):
    def __init__(self, number: int):

        MSG = (
            "This experiment is an implementation of Patrick Loeber's Famous "
            "AI Snake Game. You are in charge of the experiment."
        )

        super().__init__(MSG)
