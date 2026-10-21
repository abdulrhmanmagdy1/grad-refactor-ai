"""Project review runs: storage, a background worker, decisions and downloads.

Running a project's own tests is allowed only when the service is started with
REFACTOR_AI_PROJECT_TESTS=true, because the tests execute the uploaded code on this machine;
a request to run them is otherwise recorded as a warning and ignored.

A submitted zip is checked and extracted at once (problems are answered immediately);
the review itself runs on one worker thread, one project at a time, from a bounded queue.
Records are kept as JSON in SQLite next to the run history, and each project's files in
their own folder; deleting a project removes both. A record still queued or running when
the service stops is marked failed with the code interrupted at the next start; it is never
restarted.

The accepted fixes of a project can be downloaded as one unified diff or as a zip of the
project with them applied. A fix is located by its function's name and original text, so
several accepted fixes in one file apply in any order.
"""

from __future__ import annotations

import ast
import io
import json
import logging
import queue
import shutil
import sqlite3
import threading
import uuid
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from refactor_ai.project import fixes
from refactor_ai.project.models import Fix, ProjectRecord, ProjectStatus
from refactor_ai.project.review import ProjectReviewer, ReviewSettings
from refactor_ai.project.testrun import ProjectTestRunner
from refactor_ai.project.workspace import extract_project, open_workspace

logger = logging.getLogger(__name__)

FILES_FOLDER = "files"
TERMINAL = (ProjectStatus.COMPLETED, ProjectStatus.FAILED)
DECISIONS = ("accepted", "rejected")


def _now() -> datetime:
    return datetime.now(UTC)


class ProjectBusy(Exception):
    """The queue is full."""


class ProjectStore:
    """Project records as JSON in SQLite; thread-safe."""

    def __init__(self, path: Path, retention: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.retention = retention
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS projects (project_id TEXT PRIMARY KEY, "
            "seq INTEGER NOT NULL, status TEXT NOT NULL, record TEXT NOT NULL)"
        )

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def save(self, record: ProjectRecord) -> None:
        data = record.model_dump_json()
        with self._lock:
            self._db.execute(
                "INSERT INTO projects (project_id, seq, status, record) VALUES (?, "
                "(SELECT COALESCE(MAX(seq), 0) + 1 FROM projects), ?, ?) "
                "ON CONFLICT(project_id) DO UPDATE SET status = excluded.status, "
                "record = excluded.record",
                (record.project_id, record.status.value, data),
            )

    def get(self, project_id: str) -> ProjectRecord | None:
        with self._lock:
            row = self._db.execute(
                "SELECT record FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
        return ProjectRecord.model_validate_json(row[0]) if row else None

    def list(self, limit: int) -> list[ProjectRecord]:
        with self._lock:
            rows = self._db.execute(
                "SELECT record FROM projects ORDER BY seq DESC LIMIT ?", (limit,)
            ).fetchall()
        return [ProjectRecord.model_validate_json(row[0]) for row in rows]

    def delete(self, project_id: str) -> bool:
        with self._lock:
            cursor = self._db.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
        return cursor.rowcount > 0

    def unfinished(self) -> list[ProjectRecord]:
        with self._lock:
            rows = self._db.execute(
                "SELECT record FROM projects WHERE status NOT IN (?, ?)",
                tuple(status.value for status in TERMINAL),
            ).fetchall()
        return [ProjectRecord.model_validate_json(row[0]) for row in rows]

    def beyond_retention(self) -> list[str]:
        """Finished projects outside the newest `retention` projects (unfinished ones stay)."""
        with self._lock:
            rows = self._db.execute(
                "SELECT project_id, status FROM projects ORDER BY seq DESC"
            ).fetchall()
        finished = {status.value for status in TERMINAL}
        return [pid for pid, status in rows[self.retention :] if status in finished]


class ProjectService:
    def __init__(
        self,
        store: ProjectStore,
        root: Path,
        *,
        provider_factory: Callable[[], object | None] = lambda: None,
        settings: ReviewSettings | None = None,
        test_runner: ProjectTestRunner | None = None,
        max_pending: int = 2,
        tests_allowed: bool = False,
    ) -> None:
        self.store = store
        self.root = root
        self.provider_factory = provider_factory
        self.settings = settings or ReviewSettings()
        self.test_runner = test_runner or ProjectTestRunner()
        self.max_pending = max_pending
        self.tests_allowed = tests_allowed
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._pending = 0
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._recover()

    # --- lifecycle ---------------------------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._work, name="refactor-ai-project-review", daemon=True
        )
        self._thread.start()

    def _recover(self) -> None:
        """Mark reviews left unfinished by an earlier service process as interrupted."""
        for record in self.store.unfinished():
            record.status = ProjectStatus.FAILED
            record.finished_at = _now()
            record.progress = None
            record.error = {
                "code": "interrupted",
                "message": "The service stopped before this review finished; it is not restarted.",
            }
            self.store.save(record)

    def stop(self, timeout: float) -> bool:
        self._queue.put(None)
        if self._thread is None:
            return True
        self._thread.join(timeout)
        return not self._thread.is_alive()

    # --- requests ----------------------------------------------------------------------

    def submit(self, data: bytes, name: str, run_tests: bool) -> ProjectRecord:
        """Check and extract the zip, store a queued record and queue the review.

        Raises IntakeError for an unusable upload and ProjectBusy when the queue is full.
        """
        with self._lock:
            if self._pending >= self.max_pending:
                raise ProjectBusy()
            self._pending += 1
        project_id = uuid.uuid4().hex
        folder = self.root / project_id
        try:
            workspace = extract_project(data, folder / FILES_FOLDER)
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            with self._lock:
                self._pending -= 1
            raise
        warnings = []
        if run_tests and not self.tests_allowed:
            warnings.append(
                "Running the project's tests was requested, but this service does not allow it "
                "(REFACTOR_AI_PROJECT_TESTS is off)."
            )
        record = ProjectRecord(
            project_id=project_id,
            name=name[:120] or "project",
            created_at=_now(),
            status=ProjectStatus.QUEUED,
            progress="Waiting to start",
            run_tests=run_tests and self.tests_allowed,
            warnings=warnings,
            skipped_files=workspace.skipped[:200],
            summary={"python_files": len(workspace.python_files), "files": len(workspace.files)},
        )
        self.store.save(record)
        self._queue.put(project_id)
        self._prune()
        return record

    def get(self, project_id: str) -> ProjectRecord | None:
        return self.store.get(project_id)

    def list(self, limit: int = 20) -> list[ProjectRecord]:
        return self.store.list(limit)

    def delete(self, project_id: str) -> bool:
        deleted = self.store.delete(project_id)
        shutil.rmtree(self.root / project_id, ignore_errors=True)
        return deleted

    def decide(self, project_id: str, fix_id: str, decision: str) -> ProjectRecord:
        """Record accept or reject for a fix of a finished project (KeyError if unknown)."""
        if decision not in DECISIONS:
            raise ValueError(f"decision must be one of {DECISIONS}")
        record = self.store.get(project_id)
        if record is None:
            raise KeyError("project")
        if record.status is not ProjectStatus.COMPLETED:
            raise LookupError("The review has not finished.")
        fix = next((f for f in record.fixes if f.id == fix_id), None)
        if fix is None:
            raise KeyError("fix")
        if fix.proposed is None or fix.diff is None:
            raise LookupError("This fix has no proposed change.")
        fix.decision = decision
        self.store.save(record)
        return record

    def patched_files(self, project_id: str) -> tuple[ProjectRecord, dict[str, str]]:
        """The text of every file changed by the accepted fixes."""
        record = self.store.get(project_id)
        if record is None:
            raise KeyError("project")
        accepted = [f for f in record.fixes if f.decision == "accepted" and f.proposed]
        if not accepted:
            raise LookupError("No fix has been accepted.")
        workspace = open_workspace(self.root / project_id / FILES_FOLDER)
        changed: dict[str, str] = {}
        for fix in accepted:
            source = changed.get(fix.file) or workspace.read(fix.file)
            changed[fix.file] = apply_recorded_fix(source, fix)
        return record, changed

    def patch(self, project_id: str) -> str:
        record, changed = self.patched_files(project_id)
        workspace = open_workspace(self.root / project_id / FILES_FOLDER)
        return "".join(
            fixes.unified_diff(workspace.read(file), text, file)
            for file, text in sorted(changed.items())
        )

    def download(self, project_id: str) -> tuple[str, bytes]:
        """A zip of the project with the accepted fixes applied, and its file name."""
        record, changed = self.patched_files(project_id)
        workspace = open_workspace(self.root / project_id / FILES_FOLDER)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in workspace.files:
                if file in changed:
                    archive.writestr(file, changed[file].encode("utf-8"))
                else:
                    archive.write(workspace.path(file), file)
        stem = "".join(c if c.isalnum() or c in "-_" else "-" for c in record.name)[:60]
        return f"{stem or 'project'}-reviewed.zip", buffer.getvalue()

    # --- worker ------------------------------------------------------------------------

    def _work(self) -> None:
        while True:
            project_id = self._queue.get()
            if project_id is None:
                return
            try:
                self._review(project_id)
            except Exception:  # never let one project stop the worker
                logger.exception("The review of project %s failed", project_id)
                self._fail(project_id, "internal_error", "The review failed unexpectedly.")
            finally:
                with self._lock:
                    self._pending -= 1

    def _review(self, project_id: str) -> None:
        record = self.store.get(project_id)
        if record is None:  # deleted while it waited
            return
        record.status = ProjectStatus.INDEXING
        record.started_at = _now()
        self.store.save(record)

        def progress(status: ProjectStatus, text: str) -> None:
            current = self.store.get(project_id)
            if current is None:
                raise _Deleted()
            current.status, current.progress = status, text
            self.store.save(current)

        workspace = open_workspace(self.root / project_id / FILES_FOLDER)
        settings = ReviewSettings(**{**self.settings.__dict__, "run_tests": record.run_tests})
        reviewer = ProjectReviewer(
            workspace,
            self.provider_factory(),
            settings,
            test_runner=self.test_runner,
            on_progress=progress,
        )
        try:
            outcome = reviewer.run()
        except _Deleted:
            return
        record = self.store.get(project_id)
        if record is None:
            return
        record.status = ProjectStatus.COMPLETED
        record.finished_at = _now()
        record.progress = None
        record.summary = {**record.summary, **outcome.summary}
        record.architecture = outcome.architecture
        record.findings = outcome.findings
        record.fixes = outcome.fixes
        record.baseline_tests = outcome.baseline_tests
        record.model = outcome.model
        record.calls = outcome.calls
        record.stage_times = outcome.stage_times
        record.warnings = [*record.warnings, *outcome.warnings]
        self.store.save(record)

    def _fail(self, project_id: str, code: str, message: str) -> None:
        record = self.store.get(project_id)
        if record is None:
            return
        record.status = ProjectStatus.FAILED
        record.finished_at = _now()
        record.progress = None
        record.error = {"code": code, "message": message}
        self.store.save(record)

    def _prune(self) -> None:
        for project_id in self.store.beyond_retention():
            self.delete(project_id)


class _Deleted(Exception):
    """The project was deleted while it was reviewed."""


def apply_recorded_fix(source: str, fix: Fix) -> str:
    """Apply a stored fix to the current text of its file (located by original text)."""
    name = fix.symbol.rsplit(".", 1)[-1]
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError) as exc:
        raise LookupError(f"{fix.file} no longer parses.") from exc
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            span = fixes.function_span(source, name, node.end_lineno)
            if span is not None and fixes.function_text(source, span) == fix.original:
                proposal = fixes.Proposal(fix.proposed, tuple(fix.imports))
                return fixes.apply_fix(source, fix.file, span, proposal).patched
    raise LookupError(f"The function of fix {fix.id} was not found in {fix.file}.")


def record_summary(record: ProjectRecord) -> dict:
    """The short form of a record for lists."""
    return json.loads(
        record.model_dump_json(
            include={
                "project_id",
                "name",
                "created_at",
                "finished_at",
                "status",
                "progress",
                "run_tests",
                "summary",
                "error",
            }
        )
    )
