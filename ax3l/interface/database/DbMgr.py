"""Own MariaDB connections, SQL execution, transactions, and cleanup."""

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
import os
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from ax3l.constants.DDbMgr import DDbMgr
from ax3l.interface.database.EventSchema import EventSchema


class DbMgr:
    def __init__(self, *, database: str | None = None, initialize_event_tables: bool = True):
        self._connection = pymysql.connect(
            host=os.environ["DB_HOST"],
            port=int(os.environ.get("DB_PORT", DDbMgr.PORT)),
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            database=database if database is not None else os.environ["DB_NAME"],
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=True,
        )
        try:
            if initialize_event_tables:
                EventSchema(self).initialize()
        except Exception:
            self.close()
            raise

    def execute(
        self, sql: str, params: Sequence[Any] | Mapping[str, Any] | None = None
    ) -> int:
        """Execute parameterized SQL and return the affected row count."""
        with self._connection.cursor() as cursor:
            return cursor.execute(sql, params)

    def query(
        self, sql: str, params: Sequence[Any] | Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute parameterized SQL and return rows by column name."""
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Commit a group of writes together, or roll them back on failure.

        Transactions must not be nested. MariaDB DDL implicitly commits and
        must be kept outside these application write transactions.
        """
        self._connection.begin()
        try:
            yield
            self._connection.commit()
        except BaseException:
            self._connection.rollback()
            raise

    def close(self) -> None:
        self._connection.close()
