from ax3l.app.Prompt import Prompt


class GenerateHaiku(Prompt):
    def __init__(self):
        super().__init__("Write a haiku.")
