"""Short reference pages are reachable only through explicit internal URLs."""

import re
import unittest

from ax3l.app.snakelab.prompts.ProjectContext import ProjectContext
from ax3l.interface.KnowledgeBase import KnowledgeBase


class KnowledgeBaseTests(unittest.TestCase):
    def test_pages_stay_small_and_every_link_resolves(self):
        kb = KnowledgeBase()
        visited = set()
        pending = ['/']
        while pending:
            url = pending.pop()
            if url in visited:
                continue
            visited.add(url)
            page = kb.read(url)
            self.assertLessEqual(len(page.split()), 220, url)
            for target in re.findall(r'\]\(([^)]+)\)', page):
                self.assertIn(target, kb.PAGES)
                pending.append(target)
        self.assertEqual(visited, set(kb.PAGES))

    def test_unknown_external_and_traversal_urls_cannot_read_files(self):
        for url in ('/../selection', '/analysis/../../model', '/model.md', 'https://example.com',
                    '//model', '/model?x=1', '/model#fragment', '/%2e%2e/model'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                KnowledgeBase().read(url)

    def test_project_context_links_to_reference_material_instead_of_embedding_it(self):
        text = ProjectContext().to_md()
        self.assertLess(len(text.split()), 70)
        self.assertIn('kb_tool', text)
        self.assertIn('/selection', text)
        self.assertNotIn('24-value', text)
