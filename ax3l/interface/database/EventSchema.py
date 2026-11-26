"""Own the Ax3l event schema; initialization is idempotent."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ax3l.interface.database.DbMgr import DbMgr


class EventSchema:
    def __init__(self, db: "DbMgr"):
        self._db = db

    def initialize(self) -> None:
        statements = (
            """
            CREATE TABLE IF NOT EXISTS events (
                event_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                occurred_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                name VARCHAR(100) NOT NULL,
                category VARCHAR(50) NOT NULL,
                log_level VARCHAR(10) NOT NULL,
                process_id CHAR(36) NULL,
                parent_event_id BIGINT UNSIGNED NULL,
                source_name VARCHAR(255) NULL,
                parameter VARCHAR(100) NULL,
                ax3l_version VARCHAR(100) NULL,
                INDEX idx_event_time (occurred_at, event_id),
                INDEX idx_event_name_time (name, occurred_at),
                INDEX idx_event_process (process_id, event_id),
                FOREIGN KEY (parent_event_id) REFERENCES events(event_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS event_messages (
                event_id BIGINT UNSIGNED PRIMARY KEY,
                content LONGTEXT NOT NULL,
                FOREIGN KEY (event_id) REFERENCES events(event_id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS event_list_items (
                event_id BIGINT UNSIGNED NOT NULL,
                position INT UNSIGNED NOT NULL,
                value LONGTEXT NOT NULL,
                PRIMARY KEY (event_id, position),
                FOREIGN KEY (event_id) REFERENCES events(event_id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS event_key_values (
                event_id BIGINT UNSIGNED NOT NULL,
                entry_key VARCHAR(100) COLLATE utf8mb4_bin NOT NULL,
                value LONGTEXT NOT NULL,
                PRIMARY KEY (event_id, entry_key),
                FOREIGN KEY (event_id) REFERENCES events(event_id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
        )
        statements += ("""
            CREATE TABLE IF NOT EXISTS experiment_highscores (
                event_id BIGINT UNSIGNED PRIMARY KEY,
                simulations BIGINT UNSIGNED NOT NULL,
                score INT NOT NULL,
                seed BIGINT NULL,
                FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,)
        for statement in statements:
            self._db.execute(statement)
