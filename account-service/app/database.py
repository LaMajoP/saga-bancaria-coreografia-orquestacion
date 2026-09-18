"""PostgreSQL access owned exclusively by Account & Ledger Service."""

from collections.abc import Iterator
from contextlib import contextmanager
import os
from typing import Any
from urllib.parse import quote

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


class AccountRepository:
    """Owns transactions against the remote ``account`` schema in Supabase."""

    def __init__(self, database_url: str | None = None) -> None:
        raw_database_url = database_url or os.getenv("ACCOUNT_DATABASE_URL")
        if not raw_database_url:
            raise RuntimeError("ACCOUNT_DATABASE_URL must be configured")
        self.database_url = self._normalize_database_url(raw_database_url)
        self._connection_pool: ConnectionPool | None = None

    @staticmethod
    def _normalize_database_url(database_url: str) -> str:
        """Encode credentials and query values for a PostgreSQL URI safely."""
        base, separator, query = database_url.partition("?")
        scheme, scheme_separator, authority_and_path = base.partition("://")
        authority, path_separator, path = authority_and_path.partition("/")
        credentials, at_separator, host = authority.rpartition("@")
        if at_separator:
            username, colon, password = credentials.partition(":")
            if colon:
                authority = f"{quote(username, safe='%')}:{quote(password, safe='%')}@{host}"
        normalized_base = f"{scheme}{scheme_separator}{authority}{path_separator}{path}"
        if not separator:
            return normalized_base
        normalized_pairs = []
        for pair in query.split("&"):
            key, equals, value = pair.partition("=")
            normalized_pairs.append(f"{key}={quote(value, safe='%')}" if equals else key)
        return f"{normalized_base}?{'&'.join(normalized_pairs)}"

    def _pool(self) -> ConnectionPool:
        """One pooled set of connections per process, opened lazily.

        The connection string points at Supabase's transaction-mode pooler:
        the session-mode one caps the whole project at 15 clients, which six
        processes exhaust on their own.

        Opening a fresh TLS connection to the Supabase pooler costs around two
        seconds, while reusing a pooled one costs about 0.17 s. With several
        database operations per request, connecting per operation dominated the
        whole latency of a saga.
        """
        if self._connection_pool is None:
            self._connection_pool = ConnectionPool(
                self.database_url,
                min_size=1,
                max_size=int(os.getenv("DB_POOL_MAX_SIZE", "3")),
                timeout=30.0,
                max_idle=120.0,
                kwargs={
                    "row_factory": dict_row,
                    "sslmode": "require",
                    "connect_timeout": 10,
                    # Required by the transaction-mode pooler (port 6543),
                    # which does not support server-side prepared statements.
                    "prepare_threshold": None,
                    "keepalives": 1,
                    "keepalives_idle": 30,
                    "keepalives_interval": 10,
                    "keepalives_count": 5,
                },
                open=False,
            )
            self._connection_pool.open()
        return self._connection_pool

    def initialize(self) -> None:
        """Fail fast when the Supabase migration has not been applied."""
        with self.transaction() as connection:
            connection.execute("SELECT 1 FROM account.accounts LIMIT 1")

    @contextmanager
    def transaction(self) -> Iterator[Connection[Any]]:
        with self._pool().connection() as connection:
            with connection.transaction():
                yield connection
