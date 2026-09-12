from typing import Final


class DSnakeLab:
    ENDPOINT: Final[str] = "tcp://127.0.0.1:41970"
    TIMEOUT_MS: Final[int] = 3000
    PROTOCOL_VERSION: Final[int] = 1
    MCP_TIMEOUT_SECONDS: Final[int] = 45
    SEED_STAGNANT_ROUNDS: Final[int] = 5
    STATUS_POLL_SECONDS: Final[int] = 5

    # Number of haiku requests per run; zero repeats until stopped.
    HAIKU_COUNT: Final[int] = 0
    HAIKU_SLEEP_SECONDS: Final[int] = 5
