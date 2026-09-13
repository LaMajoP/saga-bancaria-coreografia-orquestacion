"""One-time import of the former Account Service SQLite data into Supabase.

This script is intentionally outside the service runtime. Once the migration
has been verified, SQLite is no longer used by the application.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sqlite3

import psycopg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-path", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    database_url = os.getenv("ACCOUNT_DATABASE_URL")
    if not database_url:
        raise SystemExit("ACCOUNT_DATABASE_URL must be configured")
    if not args.sqlite_path.is_file():
        raise SystemExit(f"SQLite database not found: {args.sqlite_path}")

    source = sqlite3.connect(args.sqlite_path)
    source.row_factory = sqlite3.Row
    account_count = 0
    ledger_count = 0
    try:
        with psycopg.connect(database_url, sslmode="require") as target:
            with target.transaction():
                for row in source.execute(
                    "SELECT account_id, balance, currency FROM accounts ORDER BY account_id"
                ):
                    target.execute(
                        """
                        INSERT INTO account.accounts (account_id, balance, currency)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (account_id) DO UPDATE
                        SET balance = EXCLUDED.balance,
                            currency = EXCLUDED.currency,
                            updated_at = now()
                        """,
                        (row["account_id"], row["balance"], row["currency"]),
                    )
                    account_count += 1

                for row in source.execute(
                    """
                    SELECT operation_id, transfer_id, account_id, operation, amount,
                           balance_after, status, compensated, created_at
                    FROM ledger_entries
                    ORDER BY created_at, operation_id
                    """
                ):
                    if row["balance_after"] is None:
                        raise SystemExit(
                            f"Ledger entry {row['operation_id']} has no balance_after value"
                        )
                    target.execute(
                        """
                        INSERT INTO account.ledger_entries (
                            operation_id, transfer_id, account_id, operation, amount,
                            balance_after, status, compensated, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (transfer_id, account_id, operation) DO NOTHING
                        """,
                        (
                            row["operation_id"],
                            row["transfer_id"],
                            row["account_id"],
                            row["operation"],
                            row["amount"],
                            row["balance_after"],
                            row["status"],
                            bool(row["compensated"]),
                            row["created_at"],
                        ),
                    )
                    ledger_count += 1
    finally:
        source.close()

    print(f"Imported {account_count} accounts and {ledger_count} ledger entries into Supabase.")


if __name__ == "__main__":
    main()
