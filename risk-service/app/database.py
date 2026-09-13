"""PostgreSQL access owned exclusively by Risk Service."""

from collections.abc import Iterator
from contextlib import contextmanager
import os
from typing import Any
from urllib.parse import quote

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row


class RiskDatabase:
    def __init__(self, database_url: str | None = None) -> None:
        raw_database_url = database_url or os.getenv("RISK_DATABASE_URL")
        if not raw_database_url:
            raise RuntimeError("RISK_DATABASE_URL must be configured")
        self.database_url = self._normalize_database_url(raw_database_url)

    @staticmethod
    def _normalize_database_url(database_url: str) -> str:
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
        return psycopg.connect(self.database_url, row_factory=dict_row, sslmode="require")

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("SELECT 1 FROM risk.evaluations LIMIT 1")

    @contextmanager
    def transaction(self) -> Iterator[Connection[Any]]:
        connection = self._connect()
        try:
            with connection.transaction():
                yield connection
        finally:
            connection.close()
