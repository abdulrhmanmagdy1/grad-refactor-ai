import sqlite3
import threading
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from refactor_ai.contracts import ProviderMode, RunRecord, RunStatus, WorkflowMode
from refactor_ai.runs.records import interrupted_record, new_record, new_run_id
from refactor_ai.runs.store import STORE_SCHEMA_VERSION, RunStore, StoreError, sortable_time

T0 = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


def make(created=T0, status=RunStatus.QUEUED, code="def f(x):\n    return x\n") -> RunRecord:
    record = new_record(
        run_id=new_run_id(),
        created_at=created,
        code=code,
        task_type="guard_clauses",
        workflow_mode=WorkflowMode.MULTI_ROLE,
        provider_mode=ProviderMode.FAKE,
    )
    if status != RunStatus.QUEUED:
        record = record.model_copy(update={"status": status})
    return record


@pytest.fixture
def store(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite3", retention=200)
    yield store
    store.close()


def test_creates_missing_parent_directories(tmp_path):
    path = tmp_path / "a" / "b" / "runs.sqlite3"
    store = RunStore(path, retention=5)
    try:
        assert path.exists()
        assert store.count() == 0
    finally:
        store.close()


def test_round_trip_and_unknown_id(store):
    record = make()
    assert store.insert(record) == 0
    assert store.get(record.run_id) == record
    assert store.get(new_run_id()) is None
    assert store.count() == 1


def test_duplicate_run_id_is_rejected_atomically(store):
    record = make()
    store.insert(record)
    with pytest.raises(sqlite3.IntegrityError):
        store.insert(record)
    assert store.count() == 1


def test_list_is_newest_first_with_insertion_order_for_equal_times(store):
    older = make(created=T0 - timedelta(seconds=5))
    same = [make(created=T0) for _ in range(3)]
    store.insert(older)
    for record in same:
        store.insert(record)
    listed = [r.run_id for r in store.list_recent(10)]
    assert listed == [r.run_id for r in reversed(same)] + [older.run_id]
    assert [r.run_id for r in store.list_recent(2)] == listed[:2]


def test_update_is_atomic_and_reports_missing_runs(store):
    record = make()
    store.insert(record)
    updated = store.update(
        record.run_id, lambda r: r.model_copy(update={"status": RunStatus.GENERATING})
    )
    assert updated.status == RunStatus.GENERATING
    assert store.get(record.run_id).status == RunStatus.GENERATING
    assert store.update(record.run_id, lambda r: None) == updated
    assert store.update(new_run_id(), lambda r: r) is None

    def explode(current):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        store.update(record.run_id, explode)
    assert store.get(record.run_id) == updated
    with pytest.raises(ValueError):
        store.update(record.run_id, lambda r: r.model_copy(update={"run_id": new_run_id()}))
    assert store.get(record.run_id) == updated


def test_indexed_columns_follow_the_record(tmp_path):
    path = tmp_path / "runs.sqlite3"
    store = RunStore(path, retention=10)
    record = make(created=T0)
    store.insert(record)
    store.update(record.run_id, lambda r: r.model_copy(update={"status": RunStatus.FAILED}))
    store.close()
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT status, created_at FROM runs WHERE run_id = ?", (record.run_id,)
        ).fetchone()
        indexes = {
            name for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
    finally:
        conn.close()
    assert row == ("failed", "2026-10-20T09:00:00.000000Z")
    assert {"runs_created_at", "runs_status"} <= indexes


def test_delete(store):
    record = make()
    store.insert(record)
    assert store.delete(record.run_id) is True
    assert store.get(record.run_id) is None
    assert store.delete(record.run_id) is False


def test_history_survives_reopening(tmp_path):
    path = tmp_path / "runs.sqlite3"
    first = RunStore(path, retention=10)
    records = [make(created=T0 + timedelta(seconds=i)) for i in range(3)]
    for record in records:
        first.insert(record)
    first.close()
    second = RunStore(path, retention=10)
    try:
        assert [r.run_id for r in second.list_recent(10)] == [r.run_id for r in reversed(records)]
        assert second.get(records[0].run_id) == records[0]
    finally:
        second.close()


def test_retention_prunes_oldest_finished_runs_only(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite3", retention=3)
    try:
        done = [
            make(created=T0 + timedelta(seconds=i), status=RunStatus.COMPLETED) for i in range(3)
        ]
        for record in done:
            assert store.insert(record) == 0
        newest = make(created=T0 + timedelta(seconds=10))
        assert store.insert(newest) == 1
        remaining = {r.run_id for r in store.list_recent(10)}
        assert remaining == {done[1].run_id, done[2].run_id, newest.run_id}
        # Unfinished runs are never pruned, even beyond the cap.
        waiting = [make(created=T0 + timedelta(seconds=20 + i)) for i in range(4)]
        for record in waiting:
            store.insert(record)
        remaining = {r.run_id for r in store.list_recent(10)}
        assert {r.run_id for r in waiting} | {newest.run_id} <= remaining
        assert store.count() == 5
    finally:
        store.close()


def test_lower_retention_applies_on_prune(tmp_path):
    path = tmp_path / "runs.sqlite3"
    store = RunStore(path, retention=10)
    for i in range(6):
        store.insert(make(created=T0 + timedelta(seconds=i), status=RunStatus.FAILED))
    store.close()
    store = RunStore(path, retention=2)
    try:
        assert store.prune() == 4
        assert store.count() == 2
    finally:
        store.close()


def test_recover_unfinished_marks_only_non_terminal_runs(store):
    queued = make(created=T0)
    running = make(created=T0 + timedelta(seconds=1)).model_copy(
        update={"status": RunStatus.VERIFYING, "started_at": T0 + timedelta(seconds=2)}
    )
    finished = make(created=T0 + timedelta(seconds=3), status=RunStatus.COMPLETED)
    for record in (queued, running, finished):
        store.insert(record)
    now = T0 + timedelta(minutes=5)
    recovered = store.recover_unfinished(
        lambda r: interrupted_record(r, now, started=r.started_at is not None)
    )
    assert recovered == [queued.run_id, running.run_id]
    after_running = store.get(running.run_id)
    assert after_running.status == RunStatus.FAILED
    assert after_running.error.code == "interrupted"
    assert after_running.error.stage == "verifying"
    assert after_running.finished_at == now
    assert after_running.started_at == running.started_at
    assert after_running.original_code == running.original_code
    assert after_running.settings == running.settings
    assert "not rerun" in after_running.error.message
    after_queued = store.get(queued.run_id)
    assert after_queued.error.stage == "queued"
    assert "before this run started" in after_queued.error.message
    assert store.get(finished.run_id) == finished
    assert store.recover_unfinished(lambda r: r) == []


def test_unreadable_rows_are_skipped_in_lists(tmp_path):
    path = tmp_path / "runs.sqlite3"
    store = RunStore(path, retention=10)
    good = make()
    store.insert(good)
    store.close()
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO runs (run_id, seq, created_at, status, record) VALUES (?, ?, ?, ?, ?)",
            ("f" * 32, 99, sortable_time(T0 + timedelta(hours=1)), "queued", '{"broken": 1}'),
        )
    conn.close()
    store = RunStore(path, retention=10)
    try:
        assert [r.run_id for r in store.list_recent(10)] == [good.run_id]
        with pytest.raises(ValidationError):
            store.get("f" * 32)
        assert store.recover_unfinished(lambda r: r) == [good.run_id]
    finally:
        store.close()


def test_a_second_store_on_the_same_file_is_refused(tmp_path):
    """One service process per database file: a second store would otherwise mark the
    first one's queued and running runs interrupted at its startup recovery."""
    path = tmp_path / "runs.sqlite3"
    first = RunStore(path, retention=10)
    try:
        running = make().model_copy(
            update={"status": RunStatus.VERIFYING, "started_at": T0 + timedelta(seconds=1)}
        )
        queued = make()
        first.insert(running)
        first.insert(queued)
        with pytest.raises(StoreError, match="already in use"):
            RunStore(path, retention=10)
        with pytest.raises(StoreError, match="already in use"):
            RunStore(str(path), retention=10)
        # The refused store changed nothing, and the first one keeps working.
        assert first.get(running.run_id) == running
        assert first.get(queued.run_id) == queued
        first.insert(make())
        assert first.count() == 3
    finally:
        first.close()
    second = RunStore(path, retention=10)  # closing releases the file
    try:
        assert second.count() == 3
    finally:
        second.close()


def test_a_failed_open_releases_the_file(tmp_path):
    path = tmp_path / "runs.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {STORE_SCHEMA_VERSION + 1}")
    conn.close()
    with pytest.raises(StoreError, match="schema version"):
        RunStore(path, retention=10)
    with pytest.raises(StoreError, match="schema version"):  # not "already in use"
        RunStore(path, retention=10)


def test_rejects_newer_schema_versions(tmp_path):
    path = tmp_path / "runs.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {STORE_SCHEMA_VERSION + 1}")
    conn.close()
    with pytest.raises(StoreError, match="schema version"):
        RunStore(path, retention=10)


def test_closed_store_refuses_work(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite3", retention=10)
    store.close()
    store.close()  # idempotent
    with pytest.raises(StoreError):
        store.get(new_run_id())
    with pytest.raises(StoreError):
        store.insert(make())


def test_in_memory_database():
    store = RunStore(":memory:", retention=10)
    try:
        record = make()
        store.insert(record)
        assert store.get(record.run_id) == record
    finally:
        store.close()


def test_concurrent_read_modify_write_is_serialized(store):
    record = make()
    store.insert(record)
    threads_count, increments = 8, 40

    def bump():
        for _ in range(increments):
            store.update(
                record.run_id, lambda r: r.model_copy(update={"call_count": r.call_count + 1})
            )
            store.list_recent(5)

    threads = [threading.Thread(target=bump) for _ in range(threads_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert all(not thread.is_alive() for thread in threads)
    assert store.get(record.run_id).call_count == threads_count * increments


def test_sortable_time_is_fixed_width_utc():
    plus_two = datetime(2026, 10, 20, 11, 0, tzinfo=UTC).astimezone(timezone(timedelta(hours=2)))
    assert sortable_time(plus_two) == "2026-10-20T11:00:00.000000Z"
    assert sortable_time(datetime(2026, 1, 2, 3, 4, 5, 6)) == "2026-01-02T03:04:05.000006Z"
    later = sortable_time(T0 + timedelta(microseconds=1))
    assert sortable_time(T0) < later
