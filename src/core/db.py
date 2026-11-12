"""SQLite persistence layer for run records, latency tracking,
and audit trail (FR07, FR10, ADR09).
"""

import json
import sqlite3
import statistics
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from core.schemas import (
    AgentTrace,
    ASTFinding,
    ASTGraph,
    RunRecord,
    RunStatus,
    VerificationResult,
)

DEFAULT_DB_PATH = Path("runs.sqlite3")

# SQLite waits instead of failing immediately when another writer holds the lock.
# The web client polls a run while the background worker writes to it, so a
# busy timeout is what keeps that race from surfacing as "database is locked".
BUSY_TIMEOUT_MS = 5000


def _load_json(raw: str | None) -> object | None:
    """Parse a JSON column, tolerating empty or corrupted values."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _mean(values: list[float]) -> float | None:
    return round(statistics.mean(values), 2) if values else None


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 2) if values else None


def _total_tokens(metrics: dict) -> float | None:
    """Total tokens used by a run across the recorded metrics layouts.

    Current runs store ``metrics.tokens.total_tokens`` alongside the flat
    ``generated_tokens_total``; older records may carry a top-level
    ``total_tokens``. Reading all three keeps the aggregate honest instead of
    reporting null while the history has real counts.
    """
    nested = metrics.get("tokens")
    if isinstance(nested, dict):
        value = nested.get("total_tokens")
        if isinstance(value, (int, float)):
            return float(value)
    for key in ("generated_tokens_total", "total_tokens"):
        value = metrics.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _configure_connection(conn: sqlite3.Connection) -> None:
    """Apply the pragmas every connection needs (WAL is set once per file)."""
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS};")
    conn.execute("PRAGMA synchronous = NORMAL;")


class DatabaseManager:
    """Manages SQLite database connections and table lifecycle."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = str(db_path)
        self._shared_conn: sqlite3.Connection | None = None
        if self.db_path == ":memory:":
            self._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
            _configure_connection(self._shared_conn)
        self.init_db()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        if self._shared_conn is not None:
            yield self._shared_conn
            self._shared_conn.commit()
            return

        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        _configure_connection(conn)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        """Initialize tables and indexes with WAL mode enabled."""
        with self.get_connection() as conn:
            if self.db_path != ":memory:":
                conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS};")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_code TEXT NOT NULL,
                    refactoring_type TEXT,
                    output_code TEXT,
                    diff TEXT,
                    explanation TEXT,
                    metrics TEXT NOT NULL,
                    metrics_before TEXT,
                    metrics_after TEXT,
                    metrics_delta TEXT,
                    agent_traces TEXT,
                    auto_generated_tests TEXT,
                    ast_graph_before TEXT,
                    ast_graph_after TEXT,
                    errors TEXT,
                    user_feedback TEXT,
                    feedback_comment TEXT,
                    verification TEXT,
                    findings TEXT
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs (created_at DESC);
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_runs_status ON runs (status);
                """
            )
            self._ensure_columns(conn)

    @staticmethod
    def _ensure_columns(conn: sqlite3.Connection) -> None:
        """Add columns introduced after an earlier database was created (idempotent)."""
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(runs)")}
        for column, definition in (
            ("refactoring_type", "TEXT"),
            ("metrics_before", "TEXT"),
            ("metrics_after", "TEXT"),
            ("metrics_delta", "TEXT"),
            ("agent_traces", "TEXT"),
            ("auto_generated_tests", "TEXT"),
            ("ast_graph_before", "TEXT"),
            ("ast_graph_after", "TEXT"),
        ):
            if column not in existing:
                conn.execute(f"ALTER TABLE runs ADD COLUMN {column} {definition}")

    def create_run(self, run: RunRecord) -> None:
        """Insert a newly queued or created run record.

        The statement is an upsert: the async route inserts the queued record
        first and the background worker then re-inserts the same identifier
        before executing the workflow, so a plain INSERT would fail with a
        duplicate-key error and leave the run stuck in ``queued``.
        """
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs (
                    id, created_at, status, input_code, refactoring_type, output_code, diff,
                    explanation, metrics, metrics_before, metrics_after, metrics_delta,
                    agent_traces, auto_generated_tests, ast_graph_before, ast_graph_after,
                    errors, user_feedback, feedback_comment, verification, findings
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.created_at,
                    run.status.value,
                    run.input_code,
                    run.refactoring_type,
                    run.output_code,
                    run.diff,
                    run.explanation,
                    json.dumps(run.metrics or {}),
                    self._dump_json(run.metrics_before),
                    self._dump_json(run.metrics_after),
                    self._dump_json(run.metrics_delta),
                    json.dumps([trace.model_dump() for trace in run.agent_traces]),
                    run.auto_generated_tests,
                    self._dump_model(run.ast_graph_before),
                    self._dump_model(run.ast_graph_after),
                    run.errors,
                    run.user_feedback,
                    run.feedback_comment,
                    json.dumps(run.verification.model_dump()) if run.verification else None,
                    json.dumps([f.model_dump() for f in run.findings]),
                ),
            )

    def run_statistics(self, max_rows: int = 10_000) -> dict:
        """Aggregate measured run statistics (status, verdict, duration, tokens).

        Only the light columns are read, and the sample is capped: when the
        history is larger than the cap the result reports ``truncated`` so the
        numbers are never presented as covering more runs than they do.
        """
        with self.get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) AS n FROM runs").fetchone()["n"]
            rows = conn.execute(
                "SELECT status, verification, metrics FROM runs ORDER BY created_at DESC LIMIT ?",
                (max_rows,),
            ).fetchall()

        by_status: dict[str, int] = {}
        by_verdict: dict[str, int] = {}
        durations: list[float] = []
        tokens: list[float] = []
        accepted = 0
        with_verdict = 0

        for row in rows:
            status = row["status"]
            by_status[status] = by_status.get(status, 0) + 1

            verification = _load_json(row["verification"])
            if isinstance(verification, dict):
                verdict = verification.get("review_verdict")
                if isinstance(verdict, str):
                    by_verdict[verdict] = by_verdict.get(verdict, 0) + 1
                    with_verdict += 1
                    if verdict == "approved":
                        accepted += 1

            metrics = _load_json(row["metrics"])
            if isinstance(metrics, dict):
                duration = metrics.get("total_duration_ms")
                if isinstance(duration, (int, float)):
                    durations.append(float(duration))
                token_count = _total_tokens(metrics)
                if token_count is not None:
                    tokens.append(token_count)

        return {
            "total_runs": total,
            "sampled_runs": len(rows),
            "truncated": total > len(rows),
            "by_status": by_status,
            "by_verdict": by_verdict,
            "mean_duration_ms": _mean(durations),
            "median_duration_ms": _median(durations),
            "mean_total_tokens": _mean(tokens),
            "acceptance_rate": round(accepted / with_verdict, 4) if with_verdict else None,
            "runs_with_verdict": with_verdict,
        }

    def update_run(self, run: RunRecord) -> None:
        """Update state, outputs, diff, metrics, and error diagnostics for a run."""
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE runs SET
                    status = ?,
                    refactoring_type = ?,
                    output_code = ?,
                    diff = ?,
                    explanation = ?,
                    metrics = ?,
                    metrics_before = ?,
                    metrics_after = ?,
                    metrics_delta = ?,
                    agent_traces = ?,
                    auto_generated_tests = ?,
                    ast_graph_before = ?,
                    ast_graph_after = ?,
                    errors = ?,
                    user_feedback = ?,
                    feedback_comment = ?,
                    verification = ?,
                    findings = ?
                WHERE id = ?
                """,
                (
                    run.status.value,
                    run.refactoring_type,
                    run.output_code,
                    run.diff,
                    run.explanation,
                    json.dumps(run.metrics or {}),
                    self._dump_json(run.metrics_before),
                    self._dump_json(run.metrics_after),
                    self._dump_json(run.metrics_delta),
                    json.dumps([trace.model_dump() for trace in run.agent_traces]),
                    run.auto_generated_tests,
                    self._dump_model(run.ast_graph_before),
                    self._dump_model(run.ast_graph_after),
                    run.errors,
                    run.user_feedback,
                    run.feedback_comment,
                    json.dumps(run.verification.model_dump()) if run.verification else None,
                    json.dumps([f.model_dump() for f in run.findings]),
                    run.id,
                ),
            )

    @staticmethod
    def _dump_json(value: dict) -> str | None:
        return json.dumps(value) if value else None

    @staticmethod
    def _dump_model(value) -> str | None:
        return json.dumps(value.model_dump()) if value is not None else None

    def get_run(self, run_id: str) -> RunRecord | None:
        """Retrieve a specific run by its UUID."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_run_record(row)

    def list_runs(self, limit: int = 50, offset: int = 0) -> list[RunRecord]:
        """List past runs ordered by timestamp descending."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = cursor.fetchall()
            return [self._row_to_run_record(row) for row in rows]

    def recover_interrupted_runs(self) -> list[str]:
        """Mark runs left in flight by a previous process as failed (FR07, UC03).

        The service runs a single local process, so a run recorded as ``queued``
        or ``running`` when the process starts cannot still be executing: its
        background task died with the old process. Marking it failed with an
        explicit diagnostic is honest — the alternative is a history entry that
        looks alive forever and a client that polls it indefinitely.
        """
        message = (
            "Run interrupted by a service restart before it completed; no refactoring was produced."
        )
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT id, errors FROM runs WHERE status NOT IN ('completed', 'failed')"
            ).fetchall()
            for row in rows:
                previous = (row["errors"] or "").strip()
                errors = f"{previous}\n{message}" if previous else message
                conn.execute(
                    "UPDATE runs SET status = ?, errors = ? WHERE id = ?",
                    ("failed", errors, row["id"]),
                )
        return [row["id"] for row in rows]

    def count_runs(self) -> int:
        """Total number of stored runs (for honest paging in the interface)."""
        with self.get_connection() as conn:
            return int(conn.execute("SELECT COUNT(*) AS n FROM runs").fetchone()["n"])

    def update_feedback(self, run_id: str, decision: str, comment: str | None = None) -> bool:
        """Record user acceptance or rejection of a refactoring result (FR06)."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE runs
                SET user_feedback = ?, feedback_comment = ?
                WHERE id = ?
                """,
                (decision, comment, run_id),
            )
            return cursor.rowcount > 0

    def _row_to_run_record(self, row: sqlite3.Row) -> RunRecord:
        metrics = json.loads(row["metrics"]) if row["metrics"] else {}
        verification = None
        if row["verification"]:
            verification = VerificationResult.model_validate(json.loads(row["verification"]))
        findings = []
        if row["findings"]:
            findings = [ASTFinding.model_validate(f) for f in json.loads(row["findings"])]

        return RunRecord(
            id=row["id"],
            created_at=row["created_at"],
            status=RunStatus(row["status"]),
            input_code=row["input_code"],
            refactoring_type=row["refactoring_type"],
            output_code=row["output_code"],
            diff=row["diff"],
            explanation=row["explanation"],
            metrics=metrics,
            metrics_before=self._load_json(row["metrics_before"]),
            metrics_after=self._load_json(row["metrics_after"]),
            metrics_delta=self._load_json(row["metrics_delta"]),
            agent_traces=self._load_traces(row["agent_traces"]),
            auto_generated_tests=row["auto_generated_tests"],
            ast_graph_before=self._load_graph(row["ast_graph_before"]),
            ast_graph_after=self._load_graph(row["ast_graph_after"]),
            errors=row["errors"],
            user_feedback=row["user_feedback"],
            feedback_comment=row["feedback_comment"],
            verification=verification,
            findings=findings,
        )

    @staticmethod
    def _load_json(value: str | None) -> dict:
        return json.loads(value) if value else {}

    @staticmethod
    def _load_traces(value: str | None) -> list[AgentTrace]:
        if not value:
            return []
        return [AgentTrace.model_validate(item) for item in json.loads(value)]

    @staticmethod
    def _load_graph(value: str | None) -> ASTGraph | None:
        if not value:
            return None
        return ASTGraph.model_validate(json.loads(value))


# Global default database instance
db = DatabaseManager()
