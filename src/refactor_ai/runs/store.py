"""SQLite run history: one row per run holding the complete RunRecord as JSON.

One connection is shared by the worker thread and the request threads; a lock
serializes access and every write runs in its own BEGIN IMMEDIATE transaction, so a
reader never sees half of an update. The database uses write-ahead logging. Retention
deletes the oldest finished runs when a run is created and at startup; unfinished runs
are never pruned. The database path is not exposed through the API.

A store holds an exclusive lock on `<database>.lock` from opening to close, so a second
store on the same file (another service process, or a second start whose port bind will
fail) is refused before its startup recovery can mark the live runs interrupted.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from refactor_ai.contracts import TERMINAL_STATUSES, RunRecord

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

logger = logging.getLogger(__name__)

STORE_SCHEMA_VERSION = 1
MEMORY = ":memory:"
LOCK_SUFFIX = ".lock"
_TERMINAL = tuple(sorted(status.value for status in TERMINAL_STATUSES))

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY NOT NULL,
        seq INTEGER NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        status TEXT NOT NULL,
        record TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS runs_created_at ON runs (created_at, seq)",
    "CREATE INDEX IF NOT EXISTS runs_status ON runs (status)",
)


class StoreError(RuntimeError):
    """The database cannot be used (unsupported schema version or closed store)."""


def sortable_time(value: datetime) -> str:
    """Fixed-width UTC text, so the text order of created_at equals the time order."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class _ExclusiveFileLock:
    """A non-blocking exclusive lock on one file, held until release().

    The operating system releases it when the process ends. The descriptor is not
    inherited by child processes (PEP 446), so model workers and runners never hold it.
    """

    def __init__(self, path: Path, database: str) -> None:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            if sys.platform == "win32":
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            raise StoreError(
                f"The run database {database} is already in use by another service "
                "process. Run one service process per database file: stop the other "
                "process or set REFACTOR_AI_DB to another file."
            ) from None
        self._fd: int | None = fd

    def release(self) -> None:
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            if sys.platform == "win32":
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


class RunStore:
    def __init__(self, path: Path | str, retention: int) -> None:
        """Raises StoreError when another store holds the database file."""
        if retention < 1:
            raise ValueError("retention must be at least 1")
        self._retention = retention
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._file_lock: _ExclusiveFileLock | None = None
        target = str(path)
        if target != MEMORY:
            Path(target).parent.mkdir(parents=True, exist_ok=True)
            self._file_lock = _ExclusiveFileLock(Path(target + LOCK_SUFFIX), target)
        try:
            # isolation_level=None: transactions are explicit (BEGIN IMMEDIATE ... COMMIT).
            self._conn = sqlite3.connect(
                target, timeout=30.0, isolation_level=None, check_same_thread=False
            )
            self._initialize()
        except BaseException:
            self.close()
            raise

    # --- lifecycle -------------------------------------------------------------------

    def _initialize(self) -> None:
        conn = self._connection()
        # WAL keeps every transaction atomic and the file consistent after a crash; with
        # synchronous=NORMAL a commit does not wait for a disk flush, so only the last
        # commits before a power loss could be lost. (Rollback-journal commits cost about
        # 50 ms each on the Windows demonstration laptop.)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, STORE_SCHEMA_VERSION):
            raise StoreError(
                f"The run database uses schema version {version}; this service supports "
                f"version {STORE_SCHEMA_VERSION}. Use another REFACTOR_AI_DB path."
            )
        with self._transaction() as conn:
            for statement in _SCHEMA:
                conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {STORE_SCHEMA_VERSION}")

    def close(self) -> None:
        """Close the connection and release the database file for another store."""
        with self._lock:
            try:
                if self._conn is not None:
                    self._conn.close()
                    self._conn = None
            finally:
                if self._file_lock is not None:
                    self._file_lock.release()
                    self._file_lock = None

    @property
    def retention(self) -> int:
        return self._retention

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise StoreError("The run store is closed.")
        return self._conn

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = self._connection()
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.execute("COMMIT")
            except BaseException:
                # SQLite may already have rolled back (for example on a full disk).
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise

    # --- reads -----------------------------------------------------------------------

    def get(self, run_id: str) -> RunRecord | None:
        with self._lock:
            row = (
                self._connection()
                .execute("SELECT record FROM runs WHERE run_id = ?", (run_id,))
                .fetchone()
            )
        return None if row is None else RunRecord.model_validate_json(row[0])

    def list_recent(self, limit: int) -> list[RunRecord]:
        """Newest first. Rows that no longer parse are skipped and logged."""
        with self._lock:
            rows = (
                self._connection()
                .execute(
                    "SELECT run_id, record FROM runs ORDER BY created_at DESC, seq DESC LIMIT ?",
                    (limit,),
                )
                .fetchall()
            )
        records = []
        for run_id, text in rows:
            try:
                records.append(RunRecord.model_validate_json(text))
            except ValidationError:
                logger.warning("Skipping stored run %s: its record no longer validates", run_id)
        return records

    def count(self) -> int:
        with self._lock:
            return self._connection().execute("SELECT COUNT(*) FROM runs").fetchone()[0]

    # --- writes ----------------------------------------------------------------------

    def insert(self, record: RunRecord) -> int:
        """Store a new run, then apply retention. Returns the number of runs pruned."""
        with self._transaction() as conn:
            seq = conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM runs").fetchone()[0]
            conn.execute(
                "INSERT INTO runs (run_id, seq, created_at, status, record) VALUES (?, ?, ?, ?, ?)",
                (
                    record.run_id,
                    seq,
                    sortable_time(record.created_at),
                    record.status.value,
                    record.model_dump_json(),
                ),
            )
            return self._prune(conn)

    def update(
        self, run_id: str, change: Callable[[RunRecord], RunRecord | None]
    ) -> RunRecord | None:
        """Atomically replace a record with change(record).

        Returns the stored record afterwards, or None when the run does not exist (for
        example after a delete). change returning None or an equal record writes
        nothing. change runs under the store lock and must not call the store.
        """
        with self._transaction() as conn:
            row = conn.execute("SELECT record FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                return None
            current = RunRecord.model_validate_json(row[0])
            updated = change(current)
            if updated is None or updated == current:
                return current
            if updated.run_id != run_id:
                raise ValueError("An update must not change the run_id")
            conn.execute(
                "UPDATE runs SET status = ?, record = ? WHERE run_id = ?",
                (updated.status.value, updated.model_dump_json(), run_id),
            )
            return updated

    def delete(self, run_id: str) -> bool:
        with self._transaction() as conn:
            return conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,)).rowcount > 0

    def recover_unfinished(self, change: Callable[[RunRecord], RunRecord]) -> list[str]:
        """Apply change to every stored non-terminal run in one transaction.

        Used at startup to mark interrupted runs; returns their ids. Unreadable rows
        are left untouched and logged.
        """
        placeholders = ", ".join("?" for _ in _TERMINAL)
        recovered: list[str] = []
        with self._transaction() as conn:
            rows = conn.execute(
                f"SELECT run_id, record FROM runs WHERE status NOT IN ({placeholders}) "
                "ORDER BY created_at, seq",
                _TERMINAL,
            ).fetchall()
            for run_id, text in rows:
                try:
                    current = RunRecord.model_validate_json(text)
                except ValidationError:
                    logger.warning("Cannot recover stored run %s: invalid record", run_id)
                    continue
                updated = change(current)
                conn.execute(
                    "UPDATE runs SET status = ?, record = ? WHERE run_id = ?",
                    (updated.status.value, updated.model_dump_json(), run_id),
                )
                recovered.append(run_id)
        return recovered

    def prune(self) -> int:
        """Apply retention now (also done on every insert)."""
        with self._transaction() as conn:
            return self._prune(conn)

    def _prune(self, conn: sqlite3.Connection) -> int:
        total = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        excess = total - self._retention
        if excess <= 0:
            return 0
        placeholders = ", ".join("?" for _ in _TERMINAL)
        cursor = conn.execute(
            f"DELETE FROM runs WHERE run_id IN (SELECT run_id FROM runs WHERE status IN "
            f"({placeholders}) ORDER BY created_at, seq LIMIT ?)",
            (*_TERMINAL, excess),
        )
        if cursor.rowcount:
            logger.info("Retention removed %d finished run(s)", cursor.rowcount)
        return cursor.rowcount
