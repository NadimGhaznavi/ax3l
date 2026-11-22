"""Compact JSON tables preserve the values and safely display recorded reads."""

import json
from html import unescape
import unittest

from ax3l.activity.JsonMarkdown import json_markdown
from ax3l.activity.MarkdownReport import markdown_html
from ax3l.app.snakelab.prompts.ConfigurationNextStep import ConfigurationNextStep
from ax3l.app.snakelab.ParameterSpace import parameter_paths
from ax3l.presentation.snakelab.DataPages import config_page, draft_page
from ax3l.activity.ToolResult import tool_result_html
from ax3l.entities.ConfigurationDraft import ConfigurationDraft, PARAMETER_ORDER
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


class JsonMarkdownTests(unittest.TestCase):
    def render(self, page, status='ok'):
        return tool_result_html(dict(name='tool_execution_completed', content=json.dumps(
            dict(status=status, page=page))))

    def test_nested_settings_and_scalar_values_remain_readable(self):
        data = dict(model=dict(hidden_size=64, training=dict(learning_rate=.0005)),
                    enabled=True, disabled=False, score=0, missing=None, empty='', objects={}, values=[])
        text = json_markdown(data)
        self.assertIn('| training / learning rate | 0.0005 |', text)
        html = self.render(json.dumps(data))
        for expected in ('true', 'false', '0', 'null', '""', '{}', '[]'):
            self.assertIn(f'<td>{expected}</td>', unescape(html))
        self.assertEqual(html.count('<table>'), 2)
        self.assertIn('<td>hidden size</td>', html)

    def test_record_lists_share_columns_and_keep_missing_values_distinct_from_null(self):
        html = self.render(json.dumps([dict(score=38, model=dict(layers=2)), dict(score=34, extra=None)]))
        for value in ('score', 'model / layers', 'extra', '38', '34', '2', 'null', '—'):
            self.assertIn(f'>{value}</', html)
        self.assertEqual(html.count('<table>'), 1)

    def test_actual_draft_json_block_is_compact_and_keeps_every_setting(self):
        config = SimulationConfiguration.defaults()
        draft = ConfigurationDraft('draft', 'gold', {}, config)
        html = self.render(draft_page(draft))
        self.assertEqual(html.count('<table>'), 2)
        self.assertNotIn('<pre>', html)
        self.assertIn('<h1>Current draft</h1>', html)
        for parameter in PARAMETER_ORDER:
            for path in parameter_paths(parameter):
                label = ' / '.join(field.replace('_', ' ') for field in path)
                self.assertIn(f'<td>{label}</td>', html)
        self.assertIn('<td>saved settings</td>', html)
        self.assertIn('<td>current setting</td>', html)
        html = self.render(config_page('golden', 'model', config))
        self.assertIn('<td>transformer</td>', html)

    def test_markdown_characters_and_html_are_displayed_as_literal_json_values(self):
        value = '<script>alert(1)</script> | *literal* [link](javascript:alert(1))\nnext'
        html = self.render(json.dumps(dict(value=value)))
        self.assertNotIn('<script>', html)
        self.assertNotIn('<a ', html)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt; | *literal* [link](javascript:alert(1)) ↵ next', html)
        self.assertEqual(html.count('<td>'), 2)

    def test_lab_menu_paths_remain_visible_without_linking_to_report_routes(self):
        draft = ConfigurationDraft('draft', 'gold', {}, SimulationConfiguration.defaults())
        prompt = ConfigurationNextStep(draft, PARAMETER_ORDER).to_md()
        html = markdown_html(prompt)
        for path in ('/latest', '/golden', '/best', '/draft', '/guides'):
            self.assertIn(path, html)
            self.assertNotIn(f'href="{path}"', html)
        self.assertIn('Review latest simulation', html)
        self.assertIn('<td>learning rate</td>', html)
        self.assertIn('[Review latest simulation](/latest)', prompt)
        html = markdown_html('[Source](https://example.com/docs) [External](//example.com/docs) '
                             '[Unsafe](javascript:alert(1))')
        self.assertIn('<a href="https://example.com/docs">Source</a>', html)
        self.assertIn('<a href="//example.com/docs">External</a>', html)
        self.assertNotIn('href="javascript:', html)

    def test_plain_markdown_rejected_and_failed_results_are_readable(self):
        html = self.render('# Guide\n\nUse **evidence**.\n\n<script>alert(1)</script>')
        self.assertIn('<strong>evidence</strong>', html)
        self.assertNotIn('<script>', html)
        html = tool_result_html(dict(name='tool_execution_completed', content=json.dumps(dict(
            status='rejected', prompt=dict(role='user', content='Unknown data path.')))))
        self.assertIn('Rejected.', html)
        self.assertIn('Unknown data path.', html)
        self.assertIn('Read failed', tool_result_html(dict(name='tool_execution_failed', content='Read failed')))

    def test_scalar_lists_and_empty_root_values(self):
        self.assertIn('| 0 |', json_markdown([0, False, None]))
        for value, expected in ((None, 'null'), (False, 'false'), ([], '[]'), ({}, '{}')):
            self.assertIn(expected, self.render(json.dumps(value)))

    def test_model_markdown_keeps_incomplete_json_examples_and_formats_valid_blocks(self):
        html = markdown_html('Consider **these values**.\n\n```json\n{"learning_rate":\n```\n\n'
                             '```json\n{"learning_rate":0.0005}\n```')
        self.assertIn('<strong>these values</strong>', html)
        self.assertIn('<code class="language-json">', html)
        self.assertIn('<td>learning rate</td>', html)
        self.assertIn('<td>0.0005</td>', html)
