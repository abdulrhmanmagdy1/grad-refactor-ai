"""Integration tests for FastAPI endpoints (FR01, FR03, FR06, FR07, FR10, NFR01)."""

from pathlib import Path

from fastapi.testclient import TestClient

from api.app import app
from core.schemas import RunStatus

client = TestClient(app)


def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["mode"] == "production"


def test_providers_endpoint_reports_availability():
    # Phase 6: the frontend provider selector reads live availability (NFR06).
    res = client.get("/api/v1/providers")
    assert res.status_code == 200
    catalog = res.json()
    ids = {entry["id"] for entry in catalog}
    assert {"mock", "smart_ast", "ollama", "local_lora"} <= ids
    for entry in catalog:
        assert set(entry) >= {"id", "label", "available", "engine", "detail"}
        assert isinstance(entry["available"], bool)
    mock_entry = next(entry for entry in catalog if entry["id"] == "mock")
    assert mock_entry["available"] is True


def test_analyze_endpoint_valid():
    code = "def sample():\n    return 1\n"
    res = client.post("/api/v1/analyze", json={"code": code})
    assert res.status_code == 200
    data = res.json()
    assert data["syntax_valid"] is True
    assert data["findings"] == []
    assert data["metrics"]["functions_count"] == 1


def test_analyze_endpoint_rejects_empty_and_oversized():
    # Empty
    res = client.post("/api/v1/analyze", json={"code": "   "})
    assert res.status_code == 422

    # Oversized (> 20,000 chars)
    oversized = "x = 1\n" * 4000
    res = client.post("/api/v1/analyze", json={"code": oversized})
    assert res.status_code == 422


def test_analyze_endpoint_does_not_execute_code(tmp_path):
    # NFR01 guarantee
    target = tmp_path / "probe_file.txt"
    malicious = f"import os\nopen({str(target)!r}, 'w').write('hacked')\n"
    res = client.post("/api/v1/analyze", json={"code": malicious})
    assert res.status_code == 200
    assert not target.exists()


def test_create_and_poll_run_sync():
    code = "def lengthy():\n" + "    y = 2\n" * 35 + "    return y\n"
    res = client.post("/runs?sync=true", json={"code": code})
    assert res.status_code == 201
    run_data = res.json()
    run_id = run_data["id"]
    assert run_data["status"] == RunStatus.COMPLETED
    assert run_data["output_code"] is not None
    assert run_data["diff"] is not None
    # FR03: the supported refactoring type is returned with the proposal.
    assert run_data["refactoring_type"] == "extract-function"

    # Poll via GET /runs/{id}
    poll_res = client.get(f"/runs/{run_id}")
    assert poll_res.status_code == 200
    polled = poll_res.json()
    assert polled["id"] == run_id
    assert polled["status"] == RunStatus.COMPLETED
    assert polled["verification"]["syntax_valid"] is True


def test_requested_refactoring_type_is_echoed():
    # FR03: an explicitly requested refactoring type is preserved in the run record.
    code = "def simple():\n    return 1\n"
    res = client.post(
        "/runs?sync=true",
        json={"code": code, "refactoring_type": "extract-function"},
    )
    assert res.status_code == 201
    assert res.json()["refactoring_type"] == "extract-function"


def test_fr08_token_limit_fails_clearly():
    # FR08: a declared generated-token limit produces an explicit failure, not a success.
    code = "def lengthy():\n" + "    y = 2\n" * 35 + "    return y\n"
    res = client.post("/runs?sync=true", json={"code": code, "max_total_tokens": 1})
    data = res.json()
    assert data["status"] == RunStatus.FAILED
    assert "token limit" in (data["errors"] or "").lower()
    assert data["metrics"]["limits"]["max_total_tokens"] == 1


def test_get_nonexistent_run():
    res = client.get("/runs/nonexistent-uuid-1234")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_list_runs_history():
    res = client.get("/runs?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_user_feedback_acceptance_and_rejection():
    # Create a run first
    create_res = client.post("/runs?sync=true", json={"code": "def simple(): return 123"})
    run_id = create_res.json()["id"]

    # Post feedback: accepted (via the /decision alias used by the web UI)
    fb_res = client.post(
        f"/runs/{run_id}/decision",
        json={"decision": "accepted", "comment": "Great refactoring!"},
    )
    assert fb_res.status_code == 200
    updated = fb_res.json()
    assert updated["user_feedback"] == "accepted"
    assert updated["feedback_comment"] == "Great refactoring!"

    # Verify persisted in database
    get_res = client.get(f"/runs/{run_id}")
    assert get_res.json()["user_feedback"] == "accepted"

    # Reject invalid feedback decision
    invalid_fb = client.post(
        f"/runs/{run_id}/feedback",
        json={"decision": "maybe", "comment": "not sure"},
    )
    assert invalid_fb.status_code == 422


def test_frontend_served():
    res = client.get("/")
    assert res.status_code == 200
    assert "Multi-Agent Refactoring" in res.text

    # The single React interface (frontend/dist) is served at "/" (Phase 6).
    build = Path(__file__).resolve().parents[1] / "frontend" / "dist" / "index.html"
    if build.exists():
        assert 'id="root"' in res.text
        favicon = client.get("/favicon.svg")
        assert favicon.status_code == 200
