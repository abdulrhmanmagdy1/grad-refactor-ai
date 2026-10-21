"""Export of group summaries to SQLite and to CSV."""

from __future__ import annotations

import csv
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from pipeline.aggregate import GroupSummary

COLUMNS = ("group_key", "row_count", "total", "mean", "minimum", "maximum")

_INSERT = (
    f"INSERT INTO group_summary (dataset, {', '.join(COLUMNS)}) "
    f"VALUES ({', '.join('?' * (len(COLUMNS) + 1))})"
)


def open_database(path: str = ":memory:") -> sqlite3.Connection:
    """Open the export database, creating the summary table when needed."""
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS group_summary ("
        " dataset TEXT NOT NULL, group_key TEXT NOT NULL,"
        " row_count INTEGER NOT NULL, total REAL NOT NULL, mean REAL NOT NULL,"
        " minimum REAL NOT NULL, maximum REAL NOT NULL,"
        " PRIMARY KEY (dataset, group_key))"
    )
    return connection


def write_summaries(
    connection: sqlite3.Connection, dataset: str, summaries: Iterable[GroupSummary]
) -> int:
    """Replace the stored summaries of one dataset; returns the rows written."""
    rows = [
        (dataset, s.key, s.count, s.total, s.mean, s.minimum, s.maximum)
        for s in summaries
    ]
    with connection:
        connection.execute("DELETE FROM group_summary WHERE dataset = ?", (dataset,))
        connection.executemany(_INSERT, rows)
    return len(rows)


def read_summaries(connection: sqlite3.Connection, dataset: str) -> list[GroupSummary]:
    """The stored summaries of one dataset, sorted by group key."""
    cursor = connection.execute(
        "SELECT group_key, row_count, total, mean, minimum, maximum"
        " FROM group_summary WHERE dataset = ? ORDER BY group_key",
        (dataset,),
    )
    return [GroupSummary(*row) for row in cursor.fetchall()]


def write_csv(path: Path, summaries: Iterable[GroupSummary]) -> int:
    """Write summaries to a CSV file with a header line; returns the data rows."""
    count = 0
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for s in summaries:
            writer.writerow([s.key, s.count, f"{s.total:.2f}", s.mean, s.minimum, s.maximum])
            count += 1
    return count
