"""Elapsed work, exact request usage, and latest images for checklist rows."""

from datetime import datetime, timedelta
import unittest

from ax3l.activity.ExperimentActivity import item_activity
from ax3l.constants.DEventCategory import DEventCategory as Events


class ExperimentActivityTests(unittest.TestCase):
    def setUp(self):
        self.started = datetime(2026, 11, 15, 12)
        self.events = []

    def event(self, seconds, name, process='run', parent=None, **values):
        event_id = len(self.events) + 1
        event = dict(
            event_id=event_id, occurred_at=self.started + timedelta(seconds=seconds),
            observed_at=self.started + timedelta(seconds=100), process_id=process,
            parent_event_id=parent, name=name, parameter=None, source_name=None,
            task=None, tokens=None)
        event.update(values)
        self.events.append(event)
        return event_id

    def task(self, seconds, section, phase):
        return self.event(seconds, Events.SnakeLab.ANALYSIS_TASK,
                          task=dict(section=section, phase=phase))

    def test_analysis_includes_rendering_and_tool_turns_and_only_links_the_current_image(self):
        self.task(0, 'scores', 'preparing')
        self.task(5, 'scores', 'analyzing')
        conversation = self.event(5, Events.Conversation.STARTED)
        first_image = self.event(6, Events.Conversation.PROMPT, parent=conversation,
                                 parameter='simulation_summary', source_name='AnalyzeSimulation')
        self.event(15, Events.Conversation.RESPONSE, parent=conversation, tokens=80)
        self.event(25, Events.Conversation.RESPONSE, parent=conversation, tokens=120)
        self.event(26, Events.Conversation.ENDED, parent=conversation)
        self.task(27, 'scores', 'failed')
        self.task(40, 'scores', 'preparing')
        self.task(45, 'scores', 'analyzing')
        conversation = self.event(45, Events.Conversation.STARTED)
        current_image = self.event(46, Events.Conversation.PROMPT, parent=conversation,
                                   parameter='simulation_summary', source_name='AnalyzeSimulation')
        self.event(60, Events.Conversation.RESPONSE, parent=conversation, tokens=150)
        self.event(61, Events.Conversation.ENDED, parent=conversation)
        self.task(62, 'scores', 'saved')
        self.task(70, 'distribution', 'preparing')
        work = item_activity(self.events)
        self.assertEqual(work['run', 'scores'], dict(seconds=49, tokens=350, image_event_id=current_image))
        self.assertNotEqual(current_image, first_image)
        self.assertEqual(work['run', 'distribution'], dict(seconds=30, tokens=0, image_event_id=None))
        for event in self.events:
            event['observed_at'] += timedelta(seconds=10)
        refreshed = item_activity(self.events)
        self.assertEqual(refreshed['run', 'scores'], work['run', 'scores'])
        self.assertEqual(refreshed['run', 'distribution']['seconds'], 40)

    def test_configuration_conversations_include_all_requests_and_live_elapsed_time(self):
        conversation = self.event(0, Events.Conversation.STARTED, process='draft')
        self.event(1, Events.Conversation.PROMPT, process='draft', parent=conversation,
                   parameter='epsilon_pair', source_name='ProjectContext')
        self.event(1, Events.Conversation.PROMPT, process='draft', parent=conversation,
                   parameter='epsilon_pair', source_name='ConfigurationChoice')
        self.event(10, Events.Conversation.RESPONSE, process='draft', parent=conversation, tokens=50)
        self.event(15, Events.Conversation.PROMPT, process='draft', parent=conversation,
                   parameter='epsilon_pair', source_name='ToolConversation')
        self.event(30, Events.Conversation.RESPONSE, process='draft', parent=conversation, tokens=150)
        self.event(32, Events.Conversation.ENDED, process='draft', parent=conversation)
        current = self.event(40, Events.Conversation.STARTED, process='draft')
        self.event(41, Events.Conversation.PROMPT, process='draft', parent=current,
                   parameter='reward_pair')
        work = item_activity(self.events)
        self.assertEqual(work['draft', 'epsilon_pair'], dict(seconds=32, tokens=200, image_event_id=None))
        self.assertEqual(work['draft', 'reward_pair'], dict(seconds=60, tokens=0, image_event_id=None))

    def test_missing_usage_is_unknown_rather_than_zero(self):
        conversation = self.event(0, Events.Conversation.STARTED, process='draft')
        self.event(1, Events.Conversation.PROMPT, process='draft', parent=conversation,
                   parameter='hidden_size')
        self.event(10, Events.Conversation.RESPONSE, process='draft', parent=conversation, tokens=None)
        self.event(20, Events.Conversation.RESPONSE, process='draft', parent=conversation, tokens=10)
        self.event(21, Events.Conversation.ENDED, process='draft', parent=conversation)
        self.assertIsNone(item_activity(self.events)['draft', 'hidden_size']['tokens'])
        self.assertEqual(item_activity([]), {})
