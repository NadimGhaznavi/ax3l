"""Golden history joins and HTTP report navigation."""

from datetime import datetime
import json
import sqlite3
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen
from uuid import uuid4

from ax3l.app.EventLogDb import EventLogDb
from ax3l.activity.ReplyReport import reasoning_content
from ax3l.activity.GoldenConfigurations import parameter_change


class GoldenHistoryTests(unittest.TestCase):
    def test_baselines_retries_and_unrelated_conversations(self):
        connection = sqlite3.connect(':memory:')
        self.addCleanup(connection.close)
        connection.row_factory = sqlite3.Row
        connection.create_function('JSON_UNQUOTE', 1, lambda value: value)
        connection.executescript('''
            CREATE TABLE events (event_id INTEGER PRIMARY KEY, occurred_at TEXT,
                                 category TEXT, name TEXT, process_id TEXT, parameter TEXT);
            CREATE TABLE event_messages (event_id INTEGER, content TEXT);
            CREATE TABLE experiment_highscores (event_id INTEGER PRIMARY KEY, score INTEGER);
        ''')

        def event(id, category, name, process, content=None, parameter=None):
            connection.execute('INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)',
                               (id, '2026-09-15 12:00:00', category, name, process, parameter))
            if content is not None:
                connection.execute('INSERT INTO event_messages VALUES (?, ?)', (id, content))

        event(1, 'Configuration', 'golden_config_created', 'baseline')
        event(2, 'Conversation', 'prompt_sent', 'conversation', parameter='learning_rate')
        event(3, 'Conversation', 'reply_received', 'conversation', 'rejected response')
        event(4, 'Tool', 'tool_execution_completed', 'conversation', '{"status":"rejected"}')
        event(5, 'Conversation', 'prompt_sent', 'conversation', parameter='learning_rate')
        response = json.dumps({'choices': [{'message': {'reasoning_content': 'winning reason'}}]})
        event(6, 'Conversation', 'reply_received', 'conversation', response)
        event(7, 'Conversation', 'reply_received', 'unrelated', 'wrong response')
        event(8, 'Tool', 'tool_execution_completed', 'conversation', '{"status":"ok","run_id":"winner"}')
        event(9, 'Configuration', 'golden_config_created', 'winner', 'High score: 55 > 0; network.size: 4 -> 6.')
        event(10, 'Configuration', 'golden_config_retained', 'winner')
        event(11, 'Configuration', 'golden_config_created', 'seed-baseline')
        event(12, 'Tool', 'tool_execution_completed', 'unrelated', 'invalid JSON')
        event(13, 'Other', 'golden_config_created', 'wrong-category')
        connection.executemany('INSERT INTO experiment_highscores VALUES (?, ?)', [(1, 0), (9, 55)])

        class Db:
            def query(self, sql, params):
                return [dict(row) for row in connection.execute(sql.replace('%s', '?'), params)]

        rows = EventLogDb(Db()).golden_configurations()
        self.assertEqual([r['process_id'] for r in rows], ['seed-baseline', 'winner', 'baseline'])
        self.assertEqual([r['high_score'] for r in rows], [None, 55, 0])
        self.assertEqual(parameter_change(rows[1]['decision']), '4 > 6')
        self.assertEqual(parameter_change(rows[2]['decision']), '')
        self.assertEqual(rows[1]['reply_id'], 6)
        self.assertEqual(rows[1]['parameter'], 'learning_rate')
        self.assertEqual(reasoning_content(rows[1]['response']), 'winning reason')
        for row in (rows[0], rows[2]):
            self.assertIsNone(row['reply_id'])
            self.assertIsNone(row['parameter'])

    def test_missing_reasoning(self):
        for content in (None, '', 'invalid', 'null', '{}', '{"choices":[]}',
                        '{"choices":[{"message":{"content":"not reasoning"}}]}'):
            self.assertEqual(reasoning_content(content), '')

    def test_recorded_value_changes(self):
        for decision, expected in (
            (None, ''),
            ('Initial defaults', ''),
            ('Fresh baseline after seed rotation. Score to beat: 55.', ''),
            ('High score: 55 > 0; network.size: 4 -> 6.', '4 > 6'),
            ('High score: 55 > 0; learning_rate: 1e-05 -> 0.001.', '1e-05 > 0.001'),
            ('High score: 55 > 0; rewards.food: 0 -> 6; rewards.death: -4 -> -2.',
             'rewards.food: 0 > 6; rewards.death: -4 > -2'),
        ):
            with self.subTest(decision=decision):
                self.assertEqual(parameter_change(decision), expected)


class GoldenReportTests(unittest.TestCase):
    def test_table_detail_links_missing_data_and_escaping(self):
        from ax3l.server.ReportingServer import make_server

        self.enterContext(patch('ax3l.server.ReportingServer.DbMgr'))
        log = self.enterContext(patch('ax3l.server.ReportingServer.EventLogDb')).return_value
        snake = self.enterContext(patch('ax3l.server.ReportingServer.SnakeLab')).return_value
        run_id = str(uuid4())
        reason = 'Consider <script>unsafe</script>\nThen choose a value.'
        response = json.dumps({'choices': [{'message': {
            'reasoning_content': reason, 'content': 'Do not show assistant content'}}]})
        log.golden_configurations.return_value = [
            dict(event_id=9, occurred_at=datetime(2026, 9, 15, 12, 30, 45),
                 process_id=run_id, parameter='<parameter>', reply_id=6, response=response, high_score=55,
                 decision='High score: 55 > 0; network.size: 4 -> 6.'),
            dict(event_id=1, occurred_at=None, process_id=None, parameter=None,
                 reply_id=None, response=None, high_score=None),
            dict(event_id=0, occurred_at=None, process_id=None, parameter=None,
                 reply_id=None, response=None, high_score=0),
        ]
        log.get.return_value = dict(event_id=6, name='reply_received', category='Conversation', content=response)
        snake.get_config.return_value = {'seed': 42, 'training': {'learning_rate': 0.001}}
        server = make_server('127.0.0.1', 0)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        base = f'http://127.0.0.1:{server.server_port}'

        def get(path):
            with urlopen(base + path) as result:
                return result.read().decode()

        page = get('/golden-configurations')
        for value in ('Date', 'Time', 'Golden Config', 'High Score', '<td>55</td>', '<td>0</td>', 'Parameter', 'Change', '<td>4 &gt; 6</td>', 'Reason', '2026-09-15',
                      '12:30:45', '&lt;parameter&gt;', f'href="/simulations/{run_id}/config"'):
            self.assertIn(value, page)
        self.assertEqual(page.count('>Reason</a>'), 1)
        self.assertIn('href="/events/6/reason"', page)
        self.assertIn('<td></td>', page)
        page = get('/events/6/reason')
        self.assertIn('Consider &lt;script&gt;unsafe&lt;/script&gt;\nThen choose a value.', page)
        self.assertNotIn('Do not show assistant content', page)
        self.assertNotIn('<script>', page)
        self.assertIn('Back to golden configurations', page)
        config_page = get(f'/simulations/{run_id}/config')
        self.assertIn('42', config_page)
        self.assertIn('Learning Rate', config_page)
        self.assertNotIn('training.learning_rate', config_page)
        log.golden_configurations.return_value[0].update(
            parameter='reward_pair',
            decision='game.rewards.further_from_food: -4 -> -2; game.rewards.closer_to_food: -2 -> -2.')
        page = get('/golden-configurations')
        self.assertIn('Food Reward: closer, further', page)
        self.assertIn('-2 &gt; -2, -4 &gt; -2', page)
        log.get.return_value['content'] = '{}'
        with self.assertRaises(HTTPError) as error:
            get('/events/6/reason')
        self.assertEqual(error.exception.code, 404)
        log.golden_configurations.return_value = []
        self.assertIn('No golden configurations recorded.', get('/golden-configurations'))
