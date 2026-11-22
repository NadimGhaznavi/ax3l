"""One read-only browser joins local guides with privately bound data pages."""

import json
import re
import unittest
from unittest.mock import AsyncMock

from ax3l.app.snakelab.PageBrowser import PageBrowser
from ax3l.interface.KnowledgeBase import KnowledgeBase


class PageBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def test_home_links_guides_and_bound_data_without_prefetching_linked_pages(self):
        read = AsyncMock(return_value=dict(status="ok", page="[Current draft](/draft)\n[Golden](/golden)"))
        browser = PageBrowser(read)
        home = await browser.read("/")
        self.assertEqual(re.findall(r"\]\(([^)]+)\)", home["page"]), ["/draft", "/golden", "/guides"])
        read.assert_awaited_once_with("/")
        pending, visited = ["/guides"], set()
        while pending:
            url = pending.pop()
            if url in visited:
                continue
            visited.add(url)
            result = await browser.read(url)
            self.assertEqual(result["status"], "ok")
            self.assertLessEqual(len(result["page"].split()), 220)
            pending.extend(re.findall(r"\]\(([^)]+)\)", result["page"]))
        self.assertEqual(visited, set(KnowledgeBase.PAGES))
        read.assert_awaited_once()

    async def test_data_pages_rejections_and_transport_failures_keep_their_contracts(self):
        page = json.dumps(dict(seed=1970, mean=1 / 3, missing=None, notes='"quoted"\n— \\path'))
        rejection = dict(status="rejected", code="invalid_data_page", prompt=dict(role="user", content="Read /."))
        read = AsyncMock(side_effect=[dict(status="ok", page=page), rejection, rejection, TimeoutError("Unavailable")])
        browser = PageBrowser(read)
        self.assertEqual((await browser.read("/golden/scores"))["page"], page)
        self.assertEqual(await browser.read("/missing"), rejection)
        self.assertEqual(await browser.read("/"), rejection)
        with self.assertRaisesRegex(TimeoutError, "Unavailable"):
            await browser.read("/draft")
        self.assertEqual(read.await_count, 4)

    async def test_unbound_browser_can_read_guides_but_cannot_read_experiment_data(self):
        browser = PageBrowser()
        home = (await browser.read("/"))["page"]
        self.assertIn("Patrick Loeber's AI Snake Lab", home)
        self.assertEqual(re.findall(r"\]\(([^)]+)\)", home), ["/guides"])
        self.assertIn("750 episodes", (await browser.read("/guides/selection"))["page"])
        self.assertNotIn("description:", (await browser.read("/guides/selection"))["page"])
        for url in ("/guides/missing", "/guides/../../etc/passwd", "/guides/model?x=1", "/guides/model#fragment"):
            with self.subTest(url=url):
                self.assertEqual((await browser.read(url))["status"], "rejected")
        with self.assertRaisesRegex(ValueError, "bind a conversation"):
            await browser.read("/draft")
