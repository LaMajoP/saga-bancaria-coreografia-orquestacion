"""Isolated SQLite persistence for the Account & Ledger service."""

from contextlib import contextmanager
from datetime import UTC, datetime
import os
from pathlib import Path
import sqlite3
from typing import Iterator


class AccountRepository:
    """Owns the accounts and ledger tables; no other service accesses them."""

    def __init__(self, database_path: str | None = None) -> None:
        self.database_path = database_path or os.getenv(
            "ACCOUNT_DB_PATH", "/tmp/account-service.db"
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        """Create the private schema and deterministic accounts for local demos."""
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    account_id TEXT PRIMARY KEY,
                    balance INTEGER NOT NULL CHECK (balance >= 0),
                    currency TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ledger_entries (
                    operation_id TEXT PRIMARY KEY,
                    transfer_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    amount INTEGER NOT NULL CHECK (amount > 0),
                    status TEXT NOT NULL,
                    compensated INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (account_id) REFERENCES accounts(account_id),
                    UNIQUE (transfer_id, account_id, operation)
                );
                """
            )
            connection.executemany(
                """
                INSERT OR IGNORE INTO accounts (account_id, balance, currency)
                VALUES (?, ?, ?)
                """,
                [
                    ("ACC-001", 1_500_000, "COP"),
                    ("ACC-002", 1_000_000, "COP"),
                    ("ACC-003", 100_000, "COP"),
                ],
            )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def now() -> str:
        return datetime.now(UTC).isoformat()
