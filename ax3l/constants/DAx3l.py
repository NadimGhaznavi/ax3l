from typing import Final

class DAx3l:
    RAW_LOGS_ENABLED: Final[bool] = False
    HTTP_TIMEOUT_SECONDS: Final[int] = 300

    VERSION: Final[str] = "1.5.0"

    BASE_DIR: Final[str] = "/opt/prod/ax3l"
    BASE_DIR_QA: Final[str] = "/opt/qa/ax3l"

    ZMQ_ENDPOINT: Final[str] = "tcp://127.0.0.1:61970"
    ZMQ_ENDPOINT_DEV: Final[str] = "tcp://127.0.0.1:61968"
    ZMQ_ENDPOINT_QA: Final[str] = "tcp://127.0.0.1:61969"
