"""Read one explicitly addressed page of Ax3l's local reference material."""

from pathlib import Path


class KnowledgeBase:
    ROOT = Path(__file__).resolve().parents[1] / "app/snakelab/knowledge"
    PAGES = {"/": "index.md", "/analysis/": "analysis/index.md",
             "/analysis/scores": "analysis/scores.md",
             "/analysis/distribution": "analysis/distribution.md",
             "/analysis/loss": "analysis/loss.md", "/selection": "selection.md",
             "/model": "model.md", "/exploration": "exploration.md", "/rewards": "rewards.md"}

    def read(self, url: str) -> str:
        if url not in self.PAGES:
            raise ValueError("Unknown knowledge-base URL. Begin at / and follow its links.")
        return (self.ROOT / self.PAGES[url]).read_text(encoding="utf-8")
