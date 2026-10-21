"""Foundation endpoints: /health and the static /api/v1/analyze.

Migration from the foundation: /health used to answer {"status", "version", "mode":
"scaffold"}. It now returns a HealthResponse whose mode is the actual provider mode
("fake" unless REFACTOR_AI_PROVIDER=local) and needs the application lifespan, which
uvicorn always runs. /api/v1/analyze is unchanged, except that its 422 bodies now use
the ErrorResponse shape instead of FastAPI's {"detail": [...]}.
"""

import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import refactor_ai.api as api_module
from refactor_ai.api import app, create_app
from refactor_ai.config import Settings
from refactor_ai.contracts import HealthResponse
from refactor_ai.runs.testing import ScriptedWorkflow

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "docs" / "architecture" / "examples"
ENV_VARS = (
    "REFACTOR_AI_PROVIDER",
    "REFACTOR_AI_MODEL_CONFIG",
    "REFACTOR_AI_DB",
    "REFACTOR_AI_RUNNER",
    "REFACTOR_AI_MAX_PENDING",
    "REFACTOR_AI_RETENTION",
)

# /api/v1/analyze needs no lifespan, so the module-level app serves it directly.
client = TestClient(app)


SERVICE_THREADS = ("refactor-ai-",)  # the run worker and the runner self-check thread


@pytest.fixture(autouse=True)
def no_leaked_workers():
    yield
    deadline = time.monotonic() + 5
    for thread in threading.enumerate():
        if thread.name.startswith(SERVICE_THREADS):
            thread.join(max(0.0, deadline - time.monotonic()))
    alive = [t for t in threading.enumerate() if t.name.startswith(SERVICE_THREADS)]
    assert alive == [], "a service thread outlived its test"


@pytest.fixture
def clean_env(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_health_reports_the_actual_provider_mode(tmp_path):
    settings = Settings(db_path=tmp_path / "runs.sqlite3", frontend_dist=None, runner="disabled")
    with TestClient(create_app(settings, workflow=ScriptedWorkflow(), registry=[])) as test:
        response = test.get("/health")
    assert response.status_code == 200
    body = response.json()
    HealthResponse.model_validate(body)
    assert body["mode"] == "fake"
    assert body["provider"]["provider_mode"] == "fake"
    assert body == json.loads((EXAMPLES / "health_fake.json").read_text(encoding="utf-8"))


def test_module_app_reads_the_environment(clean_env, tmp_path):
    db = tmp_path / "env" / "history.sqlite3"
    clean_env.setenv("REFACTOR_AI_DB", str(db))
    clean_env.setenv("REFACTOR_AI_RUNNER", "disabled")
    clean_env.setenv("REFACTOR_AI_MAX_PENDING", "7")
    with TestClient(app) as test:
        body = test.get("/health").json()
    assert body["mode"] == "fake"
    assert body["queue"] == {"max_pending": 7, "pending": 0}
    assert body["runner"]["enabled"] is False
    assert db.exists()
    assert str(tmp_path) not in json.dumps(body)


def test_local_mode_is_reported_without_loading_a_model(clean_env, tmp_path):
    config = tmp_path / "model.local.json"
    config.write_text(
        json.dumps(
            {
                "python": "missing-python.exe",
                "model_dir": "missing-model",
                "model_id": "example/model",
                "model_revision": "0" * 40,
            }
        ),
        encoding="utf-8",
    )
    clean_env.setenv("REFACTOR_AI_PROVIDER", "local")
    clean_env.setenv("REFACTOR_AI_MODEL_CONFIG", str(config))
    clean_env.setenv("REFACTOR_AI_DB", str(tmp_path / "runs.sqlite3"))
    clean_env.setenv("REFACTOR_AI_RUNNER", "disabled")
    with TestClient(app) as test:
        body = test.get("/health").json()
        assert body["mode"] == "local_model"
        assert body["provider"]["provider_mode"] == "local_model"
        assert body["provider"]["ready"] is False
        assert body["refactor_use_adapter"] is False
        # The warm-up runs at startup; with no interpreter it stops before any process.
        runtime = app.state.runtime
        assert runtime.warmup.wait(10)
        detail = test.get("/health").json()["provider"]["detail"]
        assert detail.startswith("Model not loaded"), detail
        assert runtime.service.provider.worker_pid is None
    assert str(tmp_path) not in json.dumps(body)


def test_invalid_environment_stops_startup(clean_env, tmp_path):
    clean_env.setenv("REFACTOR_AI_DB", str(tmp_path / "runs.sqlite3"))
    clean_env.setenv("REFACTOR_AI_PROVIDER", "gpu")
    with pytest.raises(ValueError, match="REFACTOR_AI_PROVIDER"):
        with TestClient(app):
            pass
    assert app.state.runtime is None


def test_health_without_lifespan_is_service_unavailable():
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    assert api_module.app.state.runtime is None


def test_analysis_does_not_execute_code(tmp_path):
    target = tmp_path / "must-not-exist"
    code = f"from pathlib import Path\nPath({str(target)!r}).write_text('executed')"
    result = client.post("/api/v1/analyze", json={"code": code})
    assert result.status_code == 200
    assert result.json()["syntax_valid"] is True
    assert not target.exists()


def test_invalid_syntax_and_empty_input():
    result = client.post("/api/v1/analyze", json={"code": "def broken("})
    assert result.json()["syntax_valid"] is False
    assert result.json()["error"]
    for value in ("", "  ", "x" * 20001):
        response = client.post("/api/v1/analyze", json={"code": value})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
    assert client.post("/api/v1/analyze", json={"code": "x" * 20000}).status_code == 200


@pytest.mark.parametrize(
    "code",
    [
        "(" * 10000 + ")" * 10000,
        "-" * 19999 + "1",
        "+".join(["1"] * 9000),
        "not " * 4999 + "x",
    ],
    ids=["parentheses", "unary", "binary", "not-chain"],
)
def test_parser_limits_are_reported_as_invalid_syntax(code):
    """The same inputs the run API rejects as invalid_syntax; on Python 3.11 the parser
    raises MemoryError for deeply chained unary operators."""
    lenient = TestClient(app, raise_server_exceptions=False)  # a 500 is a failure, not an error
    response = lenient.post("/api/v1/analyze", json={"code": code})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["syntax_valid"] is False
    assert body["findings"] == []
    assert body["error"]


def test_long_async_function():
    code = "async def work():\n" + "    x = 1\n" * 31
    result = client.post("/api/v1/analyze", json={"code": code}).json()
    assert result["findings"][0]["rule"] == "long-function"


def test_nesting_is_structural_not_indentation():
    nested = (
        "def f(x):\n    if x:\n        for i in x:\n"
        "            while i:\n                if i > 1:\n                    break"
    )
    result = client.post("/api/v1/analyze", json={"code": nested}).json()
    assert any(f["rule"] == "deep-nesting" for f in result["findings"])
    aligned = "x = (\n                    1\n)"
    assert client.post("/api/v1/analyze", json={"code": aligned}).json()["findings"] == []


def test_analyze_example_matches_the_endpoint():
    code = (
        "def scan(rows):\n    for row in rows:\n        if row:\n            while row:\n"
        "                if row[0] > 1:\n                    break\n"
    )
    expected = json.loads((EXAMPLES / "analyze_response.json").read_text(encoding="utf-8"))
    assert client.post("/api/v1/analyze", json={"code": code}).json() == expected


def test_flat_elif_chain_is_not_deep_nesting():
    from refactor_ai.analysis import analyze

    chain = (
        "def grade(score):\n    if score >= 90:\n        return 'A'\n"
        "    elif score >= 80:\n        return 'B'\n    elif score >= 70:\n        return 'C'\n"
        "    elif score >= 60:\n        return 'D'\n    return 'F'\n"
    )
    assert analyze(chain).findings == []
