"""Read one explicitly addressed page of Ax3l's local reference material."""

from pathlib import Path


class KnowledgeBase:
    ROOT = Path(__file__).resolve().parents[1] / "presentation/snakelab/guides"
    PAGES = {"/guides": "index.md", "/guides/analysis/": "analysis/index.md",
             "/guides/analysis/scores": "analysis/scores.md",
             "/guides/analysis/distribution": "analysis/distribution.md",
             "/guides/analysis/endings": "analysis/endings.md",
             "/guides/analysis/loss": "analysis/loss.md", "/guides/selection": "choose-snake-setting/SKILL.md",
             "/guides/model": "model.md", "/guides/exploration": "exploration.md", "/guides/rewards": "rewards.md",
             "/definitions/best.md": "definitions/best.md", "/definitions/golden.md": "definitions/golden.md",
             "/definitions/latest.md": "definitions/latest.md", "/definitions/draft.md": "definitions/draft.md"}

    def read(self, url: str) -> str:
        if url not in self.PAGES:
            raise ValueError("Unknown knowledge-base URL. Begin at / and follow its links.")
        content = (self.ROOT / self.PAGES[url]).read_text(encoding="utf-8")
        return content.split("\n---\n", 1)[1].strip() if content.startswith("---\n") else content
