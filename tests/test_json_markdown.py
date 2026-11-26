"""Compact JSON tables preserve the values and safely display recorded reads."""

import json
from html import unescape
import unittest

from ax3l.presentation.reporting.JsonMarkdown import json_markdown
from ax3l.presentation.reporting.MarkdownReport import markdown_html
from ax3l.presentation.reporting.ToolResult import tool_result_html


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

    def test_grouped_configuration_settings_render_as_rows_in_status_previews(self):
        data = dict(settings={
            'learning_rate': dict(label='learning rate', values=dict(golden=.001, draft=.003), editable=False),
            'gamma': dict(label='gamma', values=dict(golden=.96, draft=.96), editable=True),
        })
        html = self.render(json.dumps(data))
        self.assertIn('<h3>settings</h3>', html)
        self.assertIn('<th>editable</th>', html)
        self.assertIn('<td>learning rate</td>', html)
        self.assertNotIn('<th>learning rate</th>', html)
        self.assertIn('golden: 0.001; draft: 0.003', html)
        self.assertIn('<td>false</td>', html)
        self.assertIn('<td>true</td>', html)

    def test_reference_rows_do_not_repeat_the_scope_in_a_field_column(self):
        data = dict(runs={name: dict(scope=name, seed=2017, high_score=score)
                          for name, score in (('best', 30), ('golden', 20), ('latest', 15))})
        html = self.render(json.dumps(data))
        self.assertIn('<th>scope</th>', html)
        self.assertNotIn('<th>Field</th>', html)
        for scope in ('best', 'golden', 'latest'):
            self.assertEqual(html.count(f'<td>{scope}</td>'), 1)

    def test_nested_measurements_display_at_most_five_decimal_places(self):
        data = dict(metrics=dict(mean_score=8.009333333333334, episodes=750,
                                 termination_reasons=dict(max_moves=dict(percent=4.266666666666667))),
                    recorded=[24.933333333333334, None, True], notes='Recorded: 8.009333333333334')
        html = self.render(json.dumps(data))
        for expected in ('8.00933', '4.26667', '24.93333', '750', 'null', 'true'):
            self.assertIn(f'<td>{expected}</td>', html)
        self.assertNotIn('4.266666666666667', html)
        self.assertIn('Recorded: 8.009333333333334', html)

    def test_nested_metric_comparisons_keep_reference_values_in_columns(self):
        data = dict(episodes=dict(best=750, golden=750, latest=750),
                    mean_score=dict(best=8.009333333333334, golden=4.5, latest=None),
                    termination_reasons=dict(wall=dict(
                        count=dict(best=187, golden=200, latest=225),
                        percent=dict(best=24.933333333333334, golden=26.666666666666668, latest=30))))
        html = self.render(json.dumps(data))
        for scope in ('best', 'golden', 'latest'):
            self.assertIn(f'<th>{scope}</th>', html)
            self.assertNotIn(f'<td>{scope}</td>', html)
        self.assertIn('<td>episodes</td>', html)
        self.assertIn('<td>termination reasons / wall / count</td>', html)
        self.assertIn('<td>termination reasons / wall / percent</td>', html)
        self.assertRegex(html, r'<td>mean score</td>\s*<td>8.00933</td>\s*<td>4.5</td>\s*<td>null</td>')
        self.assertRegex(html, r'<td>termination reasons / wall / count</td>\s*<td>187</td>\s*<td>200</td>\s*<td>225</td>')
        self.assertEqual(html.count('<table>'), 1)


    def test_markdown_characters_and_html_are_displayed_as_literal_json_values(self):
        value = '<script>alert(1)</script> | *literal* [link](javascript:alert(1))\nnext'
        html = self.render(json.dumps(dict(value=value)))
        self.assertNotIn('<script>', html)
        self.assertNotIn('<a ', html)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt; | *literal* [link](javascript:alert(1)) ↵ next', html)
        self.assertEqual(html.count('<td>'), 2)

    def test_lab_menu_paths_remain_visible_without_linking_to_report_routes(self):
        prompt = ('[Review latest simulation](/latest)\n[Golden](/golden)\n[Best](/best)\n'
                  '[Draft](/draft)\n[Reference](/guides)\n\n```json\n{"learning_rate":0.001}\n```')
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
