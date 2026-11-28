from typing import Final


class DAx3l:
    HTTP_TIMEOUT_SECONDS: Final[int] = 1800
    LLM_TIMEOUT_RETRY_SECONDS: Final[int] = 30
    SEED_ROTATION_FAILURES: Final[int] = 16

    VERSION: Final[str] = "0.5.8"
    CMDB_SUBTYPE: Final[str] = "Lab Experiment"
    CMDB_SUPPLIER: Final[str] = "Nadim-Daniel"
    CMDB_CODENAME: Final[str] = "Tensor"
    CMDB_DATABASES: Final[tuple[tuple[str, str], ...]] = (("Ax3l", "ax3l"),)

    BASE_DIR: Final[str] = "/opt/prod/ax3l"

    CONFIG_FILE: Final[str] = "conf/ax3l.json"
    LLAMASRV_URL: Final[str] = "http://127.0.0.1:51001"
    CMDB_NETWORK: Final[tuple[tuple[str, str, int], ...]] = (
        ("report", "0.0.0.0", 28870),
        ("zmq", "127.0.0.1", 61970),
    )
