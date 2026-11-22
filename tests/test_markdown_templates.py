"""Presentation edits preserve typed JSON and expose missing template values."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from jinja2 import UndefinedError

from ax3l.interface.MarkdownTemplates import MarkdownTemplates


class MarkdownTemplatesTests(unittest.TestCase):
    def test_markdown_templates_can_change_presentation_without_changing_values(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "page.md.jinja"
            path.write_text('Measured values\n```json\n{{ data | json }}\n```', encoding="utf-8")
            renderer = MarkdownTemplates(Path(folder))
            values = dict(score=0, fraction=1 / 3, missing=None, enabled=False,
                          notes='"quoted"\n— \\path {{ untouched }}')
            before = renderer.render("page.md.jinja", data=values)
            path.write_text('Settings\n```json\n{{ data | json }}\n```', encoding="utf-8")
            after = renderer.render("page.md.jinja", data=values)
            self.assertTrue(before.startswith("Measured values\n"))
            self.assertTrue(after.startswith("Settings\n"))
            self.assertEqual(json.loads(after.split("```json\n")[1].split("\n```")[0]),
                             {**values, 'fraction': .33333})
            self.assertEqual(values['fraction'], 1 / 3)
            path.write_text('{{ heading }}\n{{ data | json }}', encoding="utf-8")
            with self.assertRaises(UndefinedError):
                renderer.render("page.md.jinja", data=values)
            with self.assertRaises(ValueError):
                renderer.render("page.md.jinja", heading="Settings", data=dict(value=float("nan")))
