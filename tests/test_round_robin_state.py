import json
import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from ax3l.app.Prompt import Prompt
from ax3l.app.EventLogDb import EventLogDb
from ax3l.app.snakelab.RoundRobinState import RoundRobinState, ROUND_ROBIN_ORDER
from ax3l.app.snakelab.ToolConversation import converse
from ax3l.app.snakelab.SeedRotation import rotate_if_needed
from ax3l.app.snakelab.GenerateDefaultConfig import GenerateDefaultConfig
from ax3l.constants.DSnakeLab import DSnakeLab


class EventDb:
    """Execute checkpoint SQL against a persistent, minimal event schema."""
    def __init__(self, path):
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript('''
            CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY, name TEXT, category TEXT, process_id TEXT);
            CREATE TABLE IF NOT EXISTS event_messages (event_id INTEGER, content TEXT);
            CREATE INDEX IF NOT EXISTS event_process ON events(process_id, event_id);
            CREATE INDEX IF NOT EXISTS event_name ON events(category, name, event_id);
            CREATE INDEX IF NOT EXISTS message_event ON event_messages(event_id);
        ''')

    def query(self, sql, params):
        return [dict(row) for row in self.connection.execute(sql.replace('%s', '?'), params)]

    def log(self, name, category='Configuration', level='INFO', content='', *, process_id=None,
            parameter=None):
        with self.connection:
            event_id = self.connection.execute(
                'INSERT INTO events(name, category, process_id) VALUES (?, ?, ?)',
                (name, category, process_id)).lastrowid
            self.connection.execute('INSERT INTO event_messages VALUES (?, ?)', (event_id, content))
        return event_id


class RoundRobinTests(unittest.TestCase):


    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / 'events.db'
        self.db = EventDb(self.path)
        self.addCleanup(lambda: self.db.connection.close())
        self.order = list(ROUND_ROBIN_ORDER)

    def restart(self):
        self.db.connection.close()
        self.db = EventDb(self.path)
        return RoundRobinState(self.db).begin()

    def test_restart_during_second_parameter_retries_it_then_wraps(self):
        self.assertEqual(self.restart(), self.order[0])
        self.db.log('proposal_accepted')
        self.assertEqual(self.restart(), self.order[1])
        self.db.log('proposal_invalid')
        self.db.log('proposal_duplicate')
        self.assertEqual(self.restart(), self.order[1])
        self.assertEqual(self.restart(), self.order[1])
        for expected in self.order[2:] + self.order[:1]:
            self.db.log('proposal_accepted')
            self.assertEqual(self.restart(), expected)

    def test_lost_reply_advances_once_and_baseline_changes_preserve_position(self):
        self.restart()
        self.db.log('proposal_accepted')
        self.db.log('configuration_compared')
        self.db.log('golden_config_created')
        self.db.log('golden_config_seed_incremented')
        self.assertEqual(self.restart(), self.order[1])
        self.assertEqual(self.restart(), self.order[1])

    def test_old_or_unrelated_acceptances_do_not_advance(self):
        self.db.log('proposal_accepted')
        self.assertEqual(self.restart(), self.order[0])
        self.db.log('proposal_accepted', 'Other')
        self.assertEqual(self.restart(), self.order[0])

    def test_changed_parameter_order_stops(self):
        self.restart()
        state = RoundRobinState(self.db)
        state.order.reverse()
        with self.assertRaisesRegex(ValueError, 'parameter order changed'):
            state.begin()

    def complete_turn(self, run_id, *, improved=False):
        parameter = RoundRobinState(self.db).begin()
        self.db.log('proposal_accepted', process_id=run_id)
        self.db.log('configuration_compared', process_id=run_id)
        if improved:
            self.db.log('golden_config_created', process_id=run_id)
        return parameter







class ConversationParameterTests(unittest.IsolatedAsyncioTestCase):
    async def test_parameter_override_is_rejected_then_value_only_call_succeeds(self):
        llm = Mock(url='fixture')
        def reply(arguments):
            return (200, '', json.dumps({'choices': [{'message': {
                'role': 'assistant', 'tool_calls': [{'id': 'call-1', 'type': 'function',
                'function': {'name': 'submit_single_value',
                             'arguments': json.dumps(arguments)}}]}}]}).encode())
        llm.complete.side_effect = [reply({'parameter': 'gamma', 'value': .9}),
                                    reply({'value': 16})]
        tools = Mock(definition={'function': {'name': 'submit_single_value', 'parameters': {'properties': {'value': {}}}}}, submit=AsyncMock(return_value={'status': 'ok', 'run_id': 'next'}))
        self.assertEqual(await converse(llm, Path('/tmp'), Mock(), tools, [Prompt('test')]), {'status': 'ok', 'run_id': 'next'})
        tools.submit.assert_awaited_once_with({'value': 16})
        request = json.loads(llm.complete.call_args.args[0])
        self.assertEqual(json.loads(request['messages'][2]['content'])['status'], 'rejected')
        self.assertEqual(request['messages'][2]['tool_call_id'], 'call-1')


class ConfigurationProgressTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'events.db'
        self.db = EventDb(self.path)
        self.addCleanup(lambda: self.db.connection.close())

    def restart(self):
        self.db.connection.close()
        self.db = EventDb(self.path)
        return EventLogDb(self.db)

    def test_only_compared_configurations_count_and_repeated_events_count_once(self):
        self.db.log('golden_config_created')
        self.db.log('configuration_draft_saved', process_id='draft')
        self.db.log('proposal_accepted', process_id='run')
        self.assertEqual(self.restart().experiment_cycles(), 0)
        self.db.log('configuration_compared', process_id='run')
        self.db.log('configuration_compared', process_id='run')
        self.assertEqual(self.restart().experiment_cycles(), 1)
        self.assertEqual(self.restart().stagnant_rounds(), 1)

    def test_promotion_resets_stagnation_without_erasing_completed_cycles(self):
        self.db.log('configuration_compared', process_id='first')
        self.db.log('golden_config_created', process_id='first')
        self.assertEqual(self.restart().stagnant_rounds(), 0)
        self.db.log('configuration_compared', process_id='second')
        self.assertEqual(self.restart().stagnant_rounds(), 1)
        self.assertEqual(self.restart().experiment_cycles(), 2)

    def test_rotation_gate_counts_nine_complete_configuration_proposals(self):
        self.db.log('golden_config_created')
        for number in range(9):
            self.db.log('configuration_compared', process_id=str(number))
            self.assertEqual(self.restart().stagnant_rounds(), number + 1)
        self.db.log('golden_config_created', process_id='next-seed')
        self.assertEqual(self.restart().stagnant_rounds(), 0)
        self.assertEqual(self.restart().experiment_cycles(), 9)
