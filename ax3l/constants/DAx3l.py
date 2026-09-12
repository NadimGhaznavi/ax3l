from typing import Final

class DAx3l:
    RAW_LOGS_ENABLED: Final[bool] = False

    VERSION: Final[str] = "0.7.5"

    BASE_DIR: Final[str] = "/opt/prod/ax3l"
    BASE_DIR_QA: Final[str] = "/opt/qa/ax3l"

    PORT: Final[int] = 8081
    PORT_DEV: Final[int] = 18081
    PORT_QA: Final[int] = 28081
