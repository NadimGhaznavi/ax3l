from typing import Final


class DAx3l:
    RAW_LOGS_ENABLED: Final[bool] = False
    HTTP_TIMEOUT_SECONDS: Final[int] = 300

    VERSION: Final[str] = "3.0.1"
    CMDB_SUBTYPE: Final[str] = "Lab Experiment"
    CMDB_SUPPLIER: Final[str] = "Nadim-Daniel"
    CMDB_CODENAME: Final[str] = "Ayenanewosap"

    BASE_DIR: Final[str] = "/opt/prod/ax3l"

    ZMQ_ENDPOINT: Final[str] = "tcp://127.0.0.1:61970"
