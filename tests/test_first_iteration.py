import base64
import io
import json
from pathlib import Path
import runpy
import unittest
from unittest.mock import Mock, patch

from ax3l.app.Prompt import Prompt
from ax3l.app.snakelab.prompts.FirstContact import FirstContact
from ax3l.app.snakelab.prompts.FirstContactSingle import FirstContactSingle

FLOW = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'ax3l/app/snakelab/main-loop.py'))


class FirstIterationTests(unittest.TestCase):
    def test_idle_then_four_snapshots_logged_and_sent_once(self):
        db = Mock()
        db.log.side_effect = range(10, 30)
        llm = Mock(url='http://example')
        llm.complete.return_value = (200, '', b'{"choices":[]}')
        snake = Mock()
        snake.is_simulation_running.side_effect = [True, True, False]
        golden = Prompt('Golden configuration snapshot')
        golden.run_id = 'selected-run'
        image = {'role': 'user', 'content': [
            {'type': 'text', 'text': 'Loss for selected-run'},
            {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(b'PNG snapshot').decode()}},
        ]}
        loss = Mock()
        loss.to_json.return_value = json.dumps(image)
        flow = FLOW['run_first_iteration']
        def load_golden(db):
            self.assertEqual(snake.is_simulation_running.call_count, 3)
            return golden
        with patch.dict(flow.__globals__, {'SnakeLab': lambda: snake, 'GoldenConfig': load_golden}), patch(
            'ax3l.app.snakelab.prompts.LossPlot.LossPlot', return_value=loss
        ) as plot, patch('time.sleep') as sleep, patch('sys.stdout', new_callable=io.StringIO):
            flow(llm, Path('unused'), db)
        self.assertEqual(sleep.call_count, 2)
        plot.assert_called_once_with('selected-run')
        loss.to_json.assert_called_once_with()
        loss.refresh.assert_not_called()
        llm.complete.assert_called_once()
        messages = json.loads(llm.complete.call_args.args[0])['messages']
        self.assertEqual(messages, [json.loads(FirstContact().to_json()), json.loads(golden.to_json()), image,
                                    json.loads(FirstContactSingle('learning_rate').to_json())])
        calls = db.log.call_args_list
        self.assertEqual([call.args[0] for call in calls], [
            'conversation_started', 'prompt_sent', 'prompt_sent', 'prompt_sent', 'prompt_sent',
            'reply_received', 'conversation_ended',
        ])
        self.assertEqual([json.loads(call.args[3]) for call in calls[1:5]], messages)
        for call in calls[1:5]:
            self.assertEqual(call.kwargs['parent_event_id'], 10)
            self.assertEqual(call.kwargs['process_id'], calls[0].kwargs['process_id'])
        self.assertEqual(calls[5].kwargs['parent_event_id'], 14)

    def test_prompt_log_failure_prevents_sending(self):
        db = Mock()
        db.log.side_effect = [10, RuntimeError('DB write failed'), 11]
        llm = Mock(url='http://example')
        with self.assertRaisesRegex(RuntimeError, 'DB write failed'), patch('sys.stdout', new_callable=io.StringIO):
            FLOW['run'](llm, Path('unused'), db, count=1, prompts=[Prompt('hello')])
        llm.complete.assert_not_called()

    def test_idle_query_failure_prevents_prompt_construction(self):
        snake = Mock()
        snake.is_simulation_running.side_effect = RuntimeError('Snake Lab unavailable')
        golden = Mock()
        with patch.dict(FLOW['run_first_iteration'].__globals__, {'SnakeLab': lambda: snake, 'GoldenConfig': golden}):
            with self.assertRaisesRegex(RuntimeError, 'Snake Lab unavailable'):
                FLOW['run_first_iteration'](Mock(), Path('unused'), Mock())
        golden.assert_not_called()
