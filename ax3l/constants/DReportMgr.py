from typing import Final
from pathlib import Path


class DReportMgr:
    GIF_DIRECTORY: Final[Path] = Path("/opt/prod/ax3l/games")
    GIF_DURATION_MS: Final[int] = 75
    BACKGROUND_REFRESH_SECONDS: Final[int] = 60
    SIMULATION_BUCKET_SIZE: Final[int] = 20
    REQUEST_TIMEOUT_SECONDS: Final[int] = 30
    PORT: Final[int] = 28870
    PORT_DEV: Final[int] = 28868
    PORT_QA: Final[int] = 28869
