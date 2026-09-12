
from Prompt import Prompt

class DynamicPrompt(Prompt):

    def __init__(self, content):
        super(content=content)
        self.refresh()

    def refresh(self):
        raise NotImplemented("Sub-classes must implement this method")
