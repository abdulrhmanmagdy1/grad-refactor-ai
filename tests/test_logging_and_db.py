"""Observability and storage durability (NFR07, ADR16).

The service emits one structured JSON object per log line so a run shown in the
interface can be traced to the request that produced it, and the SQLite
connection waits for a busy lock instead of failing the request.
"""

import json
import logging
import os

from core.db import BUSY_TIMEOUT_MS, DatabaseManager
from core.logging_config import JsonFormatter, TextFormatter, configure_logging


def _record(**extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="refactor_ai.api",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="GET /runs -> 200 in 1.2ms",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_emits_one_object_per_line():
    line = JsonFormatter().format(_record(request_id="req-1", status=200, duration_ms=1.25))
    payload = json.loads(line)

    assert payload["level"] == "INFO"
    assert payload["logger"] == "refactor_ai.api"
    assert payload["request_id"] == "req-1"
    assert payload["status"] == 200
    assert payload["duration_ms"] == 1.25
    assert "timestamp" in payload


def test_text_formatter_keeps_the_extras_visible():
    line = TextFormatter().format(_record(request_id="req-2", status=404))
    assert "req-2" in line
    assert "404" in line
    assert "GET /runs" in line


def test_configure_logging_is_idempotent_and_honours_the_environment(monkeypatch):
    monkeypatch.setenv("REFACTOR_AI_LOG_FORMAT", "text")
    monkeypatch.setenv("REFACTOR_AI_LOG_LEVEL", "DEBUG")

    configure_logging(force=True)
    logger = logging.getLogger("refactor_ai")
    configure_logging(force=True)

    # Re-configuring must not stack handlers (no duplicated log lines).
    assert len(logger.handlers) == 1
    assert logger.level == logging.DEBUG
    assert isinstance(logger.handlers[0].formatter, TextFormatter)

    monkeypatch.setenv("REFACTOR_AI_LOG_FORMAT", "json")
    configure_logging(force=True)
    assert isinstance(logger.handlers[0].formatter, JsonFormatter)


def test_database_waits_for_a_busy_lock(tmp_path):
    database = DatabaseManager(tmp_path / "runs.sqlite3")
    with database.get_connection() as conn:
        timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]

    assert timeout == BUSY_TIMEOUT_MS
    assert journal.lower() == "wal"


def test_environment_default_is_json(monkeypatch):
    monkeypatch.delenv("REFACTOR_AI_LOG_FORMAT", raising=False)
    from core.logging_config import resolve_format

    assert resolve_format() == "json"
    assert os.environ.get("REFACTOR_AI_LOG_LEVEL", "INFO").upper() == "INFO"
