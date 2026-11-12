"""Operational surface of the service: aggregates, Prometheus metrics and the
concurrency guard (FR03, FR07, NFR07).
"""

from fastapi.testclient import TestClient

from agents.orchestrator import orchestrator
from api.app import app
from core.schemas import RunStatus

client = TestClient(app)

CODE = "def lengthy():\n" + "    y = 2\n" * 35 + "    return y\n"


def _create_run(**extra):
    response = client.post("/runs?sync=true", json={"code": CODE, "provider": "mock", **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_stats_report_measured_aggregates():
    _create_run()

    response = client.get("/api/v1/stats")
    assert response.status_code == 200
    stats = response.json()

    assert stats["total_runs"] >= 1
    assert stats["sampled_runs"] >= 1
    assert stats["truncated"] is False
    assert stats["by_status"].get("completed", 0) >= 1
    assert stats["by_verdict"].get("approved", 0) >= 1
    assert stats["runs_in_flight"] == 0
    assert stats["max_concurrent_runs"] >= 1
    assert 0.0 <= stats["acceptance_rate"] <= 1.0


def test_stats_never_invent_values_for_an_empty_history(tmp_path):
    from core.db import DatabaseManager

    empty = DatabaseManager(tmp_path / "empty.sqlite3")
    stats = empty.run_statistics()

    assert stats["total_runs"] == 0
    assert stats["mean_duration_ms"] is None
    assert stats["median_duration_ms"] is None
    assert stats["mean_total_tokens"] is None
    assert stats["acceptance_rate"] is None


def test_prometheus_endpoint_exposes_the_prometheus_text_format():
    _create_run()

    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")

    body = response.text
    assert "# HELP refactor_runs_total" in body
    assert "# TYPE refactor_runs_total gauge" in body
    assert 'refactor_runs_total{status="completed"}' in body
    assert "refactor_runs_in_flight 0" in body
    assert 'refactor_provider_available{provider="mock"} 1' in body


def test_run_list_carries_an_honest_total_count():
    _create_run()

    page = client.get("/runs", params={"limit": 1, "offset": 0})
    assert page.status_code == 200
    total = int(page.headers["x-total-count"])
    assert total == client.get("/api/v1/stats").json()["total_runs"]
    assert len(page.json()) <= 1

    beyond = client.get("/runs", params={"limit": 1, "offset": total})
    assert beyond.status_code == 200
    assert beyond.json() == []
    assert int(beyond.headers["x-total-count"]) == total


def test_openapi_documents_the_endpoints_by_tag():
    schema = client.get("/openapi.json").json()
    tags = {tag["name"] for tag in schema["tags"]}

    assert {"Analysis", "Runs", "Feedback", "Operations"} <= tags
    assert schema["paths"]["/runs"]["post"]["tags"] == ["Runs"]
    assert schema["paths"]["/metrics"]["get"]["tags"] == ["Operations"]


def test_recovery_marks_runs_left_in_flight_as_failed(tmp_path):
    from core.db import DatabaseManager
    from core.schemas import RunRecord, RunStatus

    database = DatabaseManager(tmp_path / "recovery.sqlite3")
    database.create_run(
        RunRecord(
            id="stuck-queued",
            created_at="2026-01-01T00:00:00+00:00",
            status=RunStatus.QUEUED,
            input_code="value = 1",
        )
    )
    database.create_run(
        RunRecord(
            id="stuck-running",
            created_at="2026-01-01T00:00:01+00:00",
            status=RunStatus.GENERATING,
            input_code="value = 2",
            errors="earlier diagnostic",
        )
    )
    database.create_run(
        RunRecord(
            id="finished",
            created_at="2026-01-01T00:00:02+00:00",
            status=RunStatus.COMPLETED,
            input_code="value = 3",
        )
    )

    recovered = database.recover_interrupted_runs()
    runs = {run.id: run for run in database.list_runs(limit=10)}

    assert sorted(recovered) == ["stuck-queued", "stuck-running"]
    assert runs["stuck-queued"].status == RunStatus.FAILED
    assert "interrupted by a service restart" in (runs["stuck-queued"].errors or "")
    assert (runs["stuck-running"].errors or "").startswith("earlier diagnostic")
    assert "interrupted by a service restart" in (runs["stuck-running"].errors or "")
    assert runs["finished"].status == RunStatus.COMPLETED


def test_stats_read_nested_token_counts(tmp_path):
    from core.db import DatabaseManager
    from core.schemas import RunRecord, RunStatus

    database = DatabaseManager(tmp_path / "tokens.sqlite3")
    database.create_run(
        RunRecord(
            id="run-tokens",
            created_at="2026-01-01T00:00:00+00:00",
            status=RunStatus.COMPLETED,
            input_code="value = 1",
            metrics={"tokens": {"total_tokens": 15}, "total_duration_ms": 120.0},
        )
    )

    stats = database.run_statistics()

    assert stats["mean_total_tokens"] == 15.0
    assert stats["mean_duration_ms"] == 120.0
    assert stats["median_duration_ms"] == 120.0


def test_concurrency_guard_rejects_a_third_concurrent_run(monkeypatch):
    monkeypatch.setattr(orchestrator, "max_concurrent_runs", 1)
    orchestrator._active_runs.add("busy-run")

    response = client.post("/runs?sync=true", json={"code": CODE, "provider": "mock"})
    assert response.status_code == 429
    assert "Too many runs in flight" in response.json()["detail"]

    orchestrator._active_runs.discard("busy-run")


def test_concurrency_guard_releases_capacity_after_a_run():
    _create_run()
    assert orchestrator.active_runs == 0
    assert orchestrator.has_capacity() is True
    assert RunStatus.COMPLETED.value in {"completed"}
