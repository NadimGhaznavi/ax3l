"""Filesystem storage for generated simulation animations."""

from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import UUID


class SimulationGifStore:
    def __init__(self, directory: Path, version: int, duration_ms: int):
        self.directory = directory / f"v{version}-{duration_ms}ms"

    def path(self, run_id: str) -> Path:
        return self.directory / f"{UUID(run_id)}.gif"

    def save(self, run_id: str, animation: bytes) -> Path:
        """Publish a complete GIF atomically, cleaning up failed writes."""
        destination = self.path(run_id)
        self.directory.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=self.directory, suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            try:
                file.write(animation)
                file.close()
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        return destination
