import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from ax3l.app.Prompt import Prompt
from ax3l.app.EventLogDb import EventLogDb
from ax3l.app.snakelab.RoundRobinState import RoundRobinState
from ax3l.app.snakelab.SingleParameters import SINGLE_PARAMETERS
from ax3l.app.snakelab.ToolConversation import converse


class EventDb:
    """Execute checkpoint SQL against a persistent, minimal event schema."""
    def __init__(self, path):
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript('''
            CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY, name TEXT, category TEXT, process_id TEXT);
            CREATE TABLE IF NOT EXISTS event_messages (event_id INTEGER, content TEXT);
        ''')

    def query(self, sql, params):
        return [dict(row) for row in self.connection.execute(sql.replace('%s', '?'), params)]

    def log(self, name, category='Configuration', level='INFO', content='', *, process_id=None):
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
        self.order = list(SINGLE_PARAMETERS)

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

    def test_stagnation_counts_three_complete_cycles_across_restart(self):
        self.db.log('golden_config_created')
        for turn in range(15):
            self.assertEqual(EventLogDb(self.db).stagnant_rounds(), turn // 5)
            self.complete_turn(str(turn))
            # Replayed comparison events must not count the run twice.
            self.db.log('configuration_compared', process_id=str(turn))
            self.db.connection.close()
            self.db = EventDb(self.path)
            self.assertEqual(EventLogDb(self.db).stagnant_rounds(), (turn + 1) // 5)

    def test_improvement_discards_partial_cycle_and_resets_stagnation(self):
        for turn in range(7):
            self.complete_turn(str(turn), improved=turn == 6)
        self.assertEqual(EventLogDb(self.db).stagnant_rounds(), 0)
        for turn in range(7, 14):
            self.complete_turn(str(turn))
            self.assertEqual(EventLogDb(self.db).stagnant_rounds(), 0)
        self.complete_turn('14')
        self.assertEqual(EventLogDb(self.db).stagnant_rounds(), 1)
        self.db.log('golden_config_created')  # Fresh seed baseline.
        self.assertEqual(EventLogDb(self.db).stagnant_rounds(), 0)

    def test_pending_last_run_does_not_finish_cycle(self):
        for turn in range(4):
            self.complete_turn(str(turn))
        self.restart()
        self.db.log('proposal_invalid')
        self.db.log('proposal_accepted', process_id='pending')
        self.assertEqual(EventLogDb(self.db).stagnant_rounds(), 0)
        self.db.log('configuration_compared', process_id='pending')
        self.assertEqual(EventLogDb(self.db).stagnant_rounds(), 1)

    def test_improvement_on_last_parameter_does_not_count_that_cycle(self):
        for turn in range(10):
            self.complete_turn(str(turn), improved=turn == 4)
            self.assertEqual(EventLogDb(self.db).stagnant_rounds(), 1 if turn == 9 else 0)


class ConversationParameterTests(unittest.IsolatedAsyncioTestCase):
    async def test_wrong_parameter_never_reaches_submission(self):
        llm = Mock(url='fixture')
        llm.complete.return_value = (200, '', json.dumps({'choices': [{'message': {
            'tool_calls': [{'function': {'name': 'submit_single_value', 'arguments':
                json.dumps({'parameter': 'gamma', 'value': .9})}}]}}]}).encode())
        tools = Mock(definition={}, submit=AsyncMock())
        with self.assertRaisesRegex(ValueError, 'may only change hidden_size'):
            await converse(llm, Path('/tmp'), Mock(), tools, [Prompt('test')], parameter='hidden_size')
        tools.submit.assert_not_awaited()
