

from Prompt import Prompt

class FirstContactSingle(Prompt):

    def __init__(self, name, desc):

        self._name = name
        self._desc = desc

        self.content(f"The paramater is {name} it can be described as {desc}")
