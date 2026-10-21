"""A SQLite log of stock movements, used for audits and the history screen."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import NamedTuple

SORTABLE_COLUMNS = frozenset({"moved_at", "sku", "bin_code", "quantity"})


class Movement(NamedTuple):
    """One change to a bin: a positive quantity went in, a negative one came out."""

    moved_at: str
    sku: str
    bin_code: str
    quantity: int
    reason: str


class MovementLog:
    """Append-only history of stock movements kept in a SQLite database."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._conn = sqlite3.connect(str(path))
        with self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS movements ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, moved_at TEXT NOT NULL, "
                "sku TEXT NOT NULL, bin_code TEXT NOT NULL, "
                "quantity INTEGER NOT NULL, reason TEXT NOT NULL)"
            )

    def record(self, movement: Movement) -> None:
        """Append one movement to the log."""
        with self._conn:
            self._conn.execute(
                "INSERT INTO movements (moved_at, sku, bin_code, quantity, reason) "
                "VALUES (?, ?, ?, ?, ?)",
                tuple(movement),
            )

    def history(self, sku: str) -> list[Movement]:
        """Every movement of ``sku``, oldest first."""
        query = (
            "SELECT moved_at, sku, bin_code, quantity, reason FROM movements "
            "WHERE sku = ? ORDER BY id"
        )
        return [Movement(*row) for row in self._conn.execute(query, (sku,))]

    def net_change(self, sku: str, bin_code: str) -> int:
        """Sum of the movements of ``sku`` in ``bin_code``; 0 when there are none."""
        row = self._conn.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM movements WHERE sku = ? AND bin_code = ?",
            (sku, bin_code),
        ).fetchone()
        return int(row[0])

    def latest(self, limit: int = 20, order_by: str = "moved_at") -> list[Movement]:
        """Up to ``limit`` movements sorted by ``order_by``, largest value first.

        ``order_by`` must be one of SORTABLE_COLUMNS; anything else raises ValueError.
        """
        if order_by not in SORTABLE_COLUMNS:
            raise ValueError(f"cannot sort movements by {order_by!r}")
        query = (
            "SELECT moved_at, sku, bin_code, quantity, reason FROM movements "
            f"ORDER BY {order_by} DESC, id DESC LIMIT ?"
        )
        return [Movement(*row) for row in self._conn.execute(query, (limit,))]

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
