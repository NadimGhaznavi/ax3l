from ax3l.app.Prompt import Prompt


class FirstContact(Prompt):
    def __init__(self):
        super().__init__(
            "This experiment trains a Transformer in Snake Lab for 500 episodes "
            "with ordinary epsilon and required EpsilonNice. Choose values that achieve "
            "the best possible high score. Sometimes your available choices all "
            "look bad. You can still gather important data by running simulations "
            "in these ranges. You may also discover a new higher plateau!"
        )
