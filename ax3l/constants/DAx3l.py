from typing import Final


class DAx3l:
    RAW_LOGS_ENABLED: Final[bool] = False
    HTTP_TIMEOUT_SECONDS: Final[int] = 300

    VERSION: Final[str] = "3.1.1"
    CMDB_SUBTYPE: Final[str] = "Lab Experiment"
    CMDB_SUPPLIER: Final[str] = "Nadim-Daniel"
    CMDB_CODENAME: Final[str] = "Yohkoh"
    CMDB_DATABASES: Final[tuple[tuple[str, str], ...]] = (("Ax3l", "ax3l"),)

    BASE_DIR: Final[str] = "/opt/prod/ax3l"

    CONFIG_FILE: Final[str] = "conf/ax3l.json"
    CMDB_NETWORK: Final[tuple[tuple[str, str, int], ...]] = (
        ("llm", "0.0.0.0", 27770),
        ("report", "0.0.0.0", 28870),
        ("zmq", "127.0.0.1", 61970),
    )
