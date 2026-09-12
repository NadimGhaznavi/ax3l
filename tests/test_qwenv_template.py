import json
from pathlib import Path
import unittest

from jinja2 import Environment
from ax3l.constants.DQwenV import DQwenV


class QwenVTemplateTests(unittest.TestCase):
    def test_images_tools_calls_and_rejection_results(self):
        template = Environment().from_string((Path(__file__).resolve().parents[1] / DQwenV.CHAT_TEMPLATE).read_text())
        arguments = {'parameter': 'learning_rate', 'value': .003}
        for args in (arguments, json.dumps(arguments)):
            messages = [
                {'role': 'user', 'content': [{'type': 'text', 'text': 'Loss comparison'},
                 {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,aGVsbG8='}}]},
                {'role': 'assistant', 'content': None, 'tool_calls': [{'function': {
                    'name': 'submit_single_value', 'arguments': args}}]},
                {'role': 'tool', 'content': '{"status":"rejected"}'},
                {'role': 'user', 'content': 'Please submit using the submit_single_value tool'},
            ]
            rendered = template.render(messages=messages, tools=[{'type': 'function', 'function': {
                'name': 'submit_single_value', 'parameters': {'type': 'object'}}}], add_generation_prompt=True)
            self.assertIn('<tools>', rendered)
            self.assertIn('Loss comparison<|vision_start|><|image_pad|><|vision_end|>', rendered)
            self.assertNotIn('data:image', rendered)
            call = json.loads(rendered.rsplit('<tool_call>\n', 1)[1].split('\n</tool_call>')[0])
            self.assertEqual(call, {'name': 'submit_single_value', 'arguments': arguments})
            self.assertIn('<tool_response>\n{"status":"rejected"}\n</tool_response>', rendered)
            self.assertTrue(rendered.endswith('<|im_start|>assistant\n'))
