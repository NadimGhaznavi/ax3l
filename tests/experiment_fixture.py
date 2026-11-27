"""A real conversation and presentation stack with in-memory persistence and control."""

import unittest
from unittest.mock import patch

from ax3l.app.experiment.ExperimentLoop import ExperimentLoop
from view_cycle_fixtures import FakeSnake, FixtureLLM, MemoryEvents, MemoryLog, MemoryStore


class ExperimentFixture(unittest.TestCase):
    def setUp(self):
        self.log = MemoryLog()
        self.store = MemoryStore(self.log)
        self.snake = FakeSnake((10,) + (9,) * 100)
        self.model = FixtureLLM()
        self.enterContext(patch('ax3l.app.experiment.ExperimentLoop.ExperimentDb', return_value=self.store))
        self.enterContext(patch('ax3l.app.experiment.ExperimentLoop.EventLogDb',
                               return_value=MemoryEvents(self.log)))
        self.shuffle = self.enterContext(patch('ax3l.app.experiment.ExperimentLoop.shuffle',
                                               side_effect=lambda names: names.reverse()))

    def loop(self):
        return ExperimentLoop(self.log, self.model, self.snake)

    def event_count(self, name):
        return sum(event['name'] == name for event in self.log.events)
