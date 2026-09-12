from ax3l.app.Prompt import Prompt


class GenerateHaiku(Prompt):
    def __init__(self, number: int):
        super().__init__(f"Write a haiku based on the number {number}.")
