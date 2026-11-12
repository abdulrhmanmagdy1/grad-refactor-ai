"""Retention for the run history (FR10): keep the newest window, never guess.

The script is destructive by nature, so the tests pin both halves of the
contract: a dry run reports without deleting, and an applied run keeps exactly
the newest ``keep`` records.
"""

import importlib.util
import sqlite3
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prune_runs.py"


def _load():
    spec = importlib.util.spec_from_file_location("prune_runs", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _seed(path: Path, count: int) -> list[str]:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, created_at TEXT NOT NULL)")
        ids = [f"run-{index:02d}" for index in range(count)]
        connection.executemany(
            "INSERT INTO runs (id, created_at) VALUES (?, ?)",
            [(run_id, f"2026-01-{index + 1:02d}T00:00:00Z") for index, run_id in enumerate(ids)],
        )
        connection.commit()
    finally:
        connection.close()
    return ids


def test_dry_run_reports_without_deleting(tmp_path):
    module = _load()
    database = tmp_path / "runs.sqlite3"
    ids = _seed(database, 7)

    report = module.prune(database, keep=3, apply=False)

    assert report["total"] == 7
    assert report["would_delete"] == 4
    assert report["deleted"] == 0
    assert report["ids"] == list(reversed(ids[:4]))  # reported newest-first

    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 7
    finally:
        connection.close()


def test_apply_keeps_exactly_the_newest_window(tmp_path):
    module = _load()
    database = tmp_path / "runs.sqlite3"
    ids = _seed(database, 7)

    report = module.prune(database, keep=3, apply=True)

    assert report["deleted"] == 4
    connection = sqlite3.connect(database)
    try:
        remaining = [
            row[0]
            for row in connection.execute("SELECT id FROM runs ORDER BY created_at").fetchall()
        ]
    finally:
        connection.close()
    assert remaining == ids[-3:]


def test_nothing_to_do_when_the_history_fits_the_window(tmp_path):
    module = _load()
    database = tmp_path / "runs.sqlite3"
    _seed(database, 3)

    report = module.prune(database, keep=10, apply=True)

    assert report["would_delete"] == 0
    assert report["deleted"] == 0
    assert report["kept"] == 3
