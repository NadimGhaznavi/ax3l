"""Serve linked guides and context-bound experiment pages through one reader."""

from collections.abc import Awaitable, Callable

from ax3l.interface.KnowledgeBase import KnowledgeBase
from ax3l.presentation.snakelab.Templates import templates


class PageBrowser:
    def __init__(self, read_data: Callable[[str], Awaitable[dict]] | None = None):
        self._read_data = read_data
        self._guides = KnowledgeBase()

    async def read(self, url: str) -> dict:
        if url == "/":
            result = await self._read_data(url) if self._read_data else {"status": "ok", "page": ""}
            if result["status"] == "ok":
                return {"status": "ok", "page": templates.render("pages/home.md.jinja", data_page=result["page"])}
            return result
        if url == "/guides" or url.startswith(("/guides/", "/definitions/")):
            try:
                return {"status": "ok", "page": self._guides.read(url)}
            except ValueError as error:
                reason = str(error)
                return {"status": "rejected", "code": "invalid_reference", "reason": reason,
                        "source_name": "KnowledgeBase", "prompt": {"role": "user", "content": reason}}
        if self._read_data is None:
            raise ValueError("Ax3l must bind a conversation before data lookup")
        return await self._read_data(url)
