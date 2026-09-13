from typing import Final


class DSnakeLab:
    DATABASE: Final[str] = "snakelab"
    ENDPOINT: Final[str] = "tcp://127.0.0.1:41970"
    TIMEOUT_MS: Final[int] = 3000
    PROTOCOL_VERSION: Final[int] = 1
    MCP_TIMEOUT_SECONDS: Final[int] = 45
    # Complete round-robin cycles without a new golden high score.
    SEED_STAGNANT_ROUNDS: Final[int] = 3
    STATUS_POLL_SECONDS: Final[int] = 5
