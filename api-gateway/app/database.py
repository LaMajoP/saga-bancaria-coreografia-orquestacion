"""PostgreSQL access owned exclusively by the API Gateway."""

from collections.abc import Iterator
from contextlib import contextmanager
import os
from typing import Any
from urllib.parse import quote

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row


class GatewayDatabase:
    def __init__(self, database_url: str | None = None) -> None:
        raw_database_url = database_url or os.getenv("GATEWAY_DATABASE_URL")
        if not raw_database_url:
            raise RuntimeError("GATEWAY_DATABASE_URL must be configured")
        self.database_url = self._normalize_database_url(raw_database_url)

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

    def _connect(self) -> Connection[Any]:
        return psycopg.connect(
            self.database_url,
            row_factory=dict_row,
            sslmode="require",
        )

    def initialize(self) -> None:
        """Fail fast when the Supabase migration has not been applied."""
        with self._connect() as connection:
            connection.execute("SELECT 1 FROM gateway.transfers LIMIT 1")

    @contextmanager
    def transaction(self) -> Iterator[Connection[Any]]:
        connection = self._connect()
        try:
            with connection.transaction():
                yield connection
        finally:
            connection.close()
