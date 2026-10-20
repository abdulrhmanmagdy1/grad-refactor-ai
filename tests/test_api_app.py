"""Application behavior: error model, CORS, static frontend, health variants, restarts."""

import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from refactor_ai.api import create_app
from refactor_ai.config import Settings
from refactor_ai.contracts import (
    GenerationResult,
    HealthResponse,
    ProviderInfo,
    ProviderMode,
    ReferenceCase,
    ReferenceTestsResult,
    RunList,
    RunnerInfo,
    RunStatus,
)
from refactor_ai.providers.base import failed_result
from refactor_ai.providers.fake import FakeProvider
from refactor_ai.runs.components import (
    RUNNER_CHECKS_RUNNING,
    RUNNER_DISABLED_REASON,
    DisabledRunner,
    UnavailableCaseRegistry,
)
from refactor_ai.runs.records import INTERRUPTED_MESSAGE, NOT_STARTED_MESSAGE
from refactor_ai.runs.service import WORKER_THREAD_NAME
from refactor_ai.runs.testing import ScriptedWorkflow

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "docs" / "architecture" / "examples"
CODE = (
    "def f(x):\n    if x is not None:\n        if x > 0:\n            return 1\n"
    "        else:\n            return 2\n    else:\n        return 0\n"
)
CASE = ReferenceCase(
    case_id="demo", task_type="guard_clauses", function_name="f", original_code=CODE
)
ALLOWED_ORIGINS = ("http://127.0.0.1:5173", "http://localhost:5173")


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


def settings_for(tmp_path, **overrides) -> Settings:
    overrides.setdefault("db_path", tmp_path / "runs.sqlite3")
    overrides.setdefault("frontend_dist", None)
    overrides.setdefault("shutdown_grace_s", 5.0)
    return Settings(**overrides)


def build(tmp_path, *, workflow=None, provider=None, runner=None, registry=None, **overrides):
    return create_app(
        settings_for(tmp_path, **overrides),
        workflow=workflow if workflow is not None else ScriptedWorkflow(),
        provider=provider if provider is not None else FakeProvider(),
        runner=runner if runner is not None else DisabledRunner("Disabled in tests."),
        registry=registry if registry is not None else [CASE],
    )


def wait_for(client, run_id, statuses=("completed", "failed"), timeout=10.0) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        body = client.get(f"/api/v1/runs/{run_id}").json()
        if body["status"] in statuses:
            return body
        if time.monotonic() > deadline:
            raise AssertionError(f"run {run_id} stayed {body['status']}")
        time.sleep(0.01)


def error_of(response) -> dict:
    body = response.json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message", "details"}
    return body["error"]


# --- error model ---------------------------------------------------------------------


def test_unknown_routes_and_trailing_slashes_are_json_404(tmp_path):
    with TestClient(build(tmp_path)) as client:
        for path in ("/nope", "/api/v1/nope", "/api/v1/runs/", "/health/", "/"):
            response = client.get(path)
            assert response.status_code == 404, path
            assert error_of(response)["code"] == "not_found"


def test_wrong_methods_are_405_with_every_allowed_method(tmp_path):
    run_path = f"/api/v1/runs/{'a' * 32}"
    cases = [
        ("PUT", "/api/v1/runs", "GET, POST"),
        ("PATCH", run_path, "DELETE, GET"),
        ("GET", f"{run_path}/decision", "POST"),
        ("POST", f"{run_path}/proposal", "GET"),
        ("POST", "/health", "GET"),
        ("GET", "/api/v1/analyze", "POST"),
    ]
    with TestClient(build(tmp_path)) as client:
        for method, path, allow in cases:
            response = client.request(method, path)
            assert response.status_code == 405, (method, path)
            assert error_of(response)["code"] == "method_not_allowed"
            assert response.headers["allow"] == allow


def test_oversized_bodies_are_rejected_before_parsing(tmp_path):
    expected = json.loads((EXAMPLES / "error_payload_too_large.json").read_text("utf-8"))
    big = json.dumps({"code": "#" * 1_100_000})
    with TestClient(build(tmp_path)) as client:
        declared = client.post(
            "/api/v1/runs", content=big, headers={"content-type": "application/json"}
        )
        assert declared.status_code == 413
        assert declared.json() == expected

        def chunks():
            for _ in range(20):
                yield b"#" * 60_000

        streamed = client.post(
            "/api/v1/analyze", content=chunks(), headers={"content-type": "application/json"}
        )
        assert streamed.status_code == 413
        assert error_of(streamed)["code"] == "payload_too_large"
        assert client.get("/api/v1/runs").json()["runs"] == []


def test_unexpected_errors_are_internal_error_without_details(tmp_path):
    class BrokenRegistry:
        def list_cases(self):
            raise RuntimeError("secret detail at C:\\Users\\x")

        def get_case(self, case_id):
            return None

    app = build(tmp_path, registry=BrokenRegistry())
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/reference-cases")
    assert response.status_code == 500
    assert response.json() == json.loads(
        (EXAMPLES / "error_internal_error.json").read_text("utf-8")
    )
    assert "secret" not in response.text and "Traceback" not in response.text


def test_invalid_case_file_makes_cases_unavailable_not_empty(tmp_path):
    registry = UnavailableCaseRegistry("ValidationError: bad case")
    with TestClient(build(tmp_path, registry=registry)) as client:
        listed = client.get("/api/v1/reference-cases")
        assert listed.status_code == 500
        assert error_of(listed)["code"] == "reference_cases_unavailable"
        with_case = client.post("/api/v1/runs", json={"code": CODE, "reference_case_id": "demo"})
        assert with_case.status_code == 500
        assert error_of(with_case)["code"] == "reference_cases_unavailable"
        without_case = client.post("/api/v1/runs", json={"code": CODE})
        assert without_case.status_code == 202
        wait_for(client, without_case.json()["run_id"])


def test_run_endpoints_need_the_lifespan(tmp_path):
    client = TestClient(build(tmp_path))  # not entered: the service never started
    for method, path in (
        ("GET", "/api/v1/runs"),
        ("POST", "/api/v1/runs"),
        ("GET", "/api/v1/reference-cases"),
        ("GET", f"/api/v1/runs/{'a' * 32}"),
    ):
        response = client.request(method, path, json={"code": CODE})
        assert response.status_code == 503, path
        assert error_of(response)["code"] == "service_unavailable"
    assert not (tmp_path / "runs.sqlite3").exists()


# --- CORS ----------------------------------------------------------------------------


@pytest.mark.parametrize("origin", ALLOWED_ORIGINS)
def test_cors_allows_the_vite_dev_server(tmp_path, origin):
    with TestClient(build(tmp_path)) as client:
        preflight = client.options(
            "/api/v1/runs",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == origin
        assert "POST" in preflight.headers["access-control-allow-methods"]
        simple = client.get("/health", headers={"Origin": origin})
        assert simple.headers["access-control-allow-origin"] == origin
        exposed = simple.headers["access-control-expose-headers"]
        assert "Content-Disposition" in exposed and "Retry-After" in exposed
        assert "access-control-allow-credentials" not in simple.headers


@pytest.mark.parametrize(
    "origin",
    ["http://evil.example", "http://localhost:3000", "https://localhost:5173", "null"],
)
def test_cors_rejects_other_origins(tmp_path, origin):
    with TestClient(build(tmp_path)) as client:
        preflight = client.options(
            "/api/v1/runs",
            headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
        )
        assert preflight.status_code == 400
        assert error_of(preflight)["code"] == "cors_rejected"
        assert "access-control-allow-origin" not in preflight.headers
        simple = client.get("/health", headers={"Origin": origin})
        assert simple.status_code == 200
        assert "access-control-allow-origin" not in simple.headers


def test_cors_rejects_methods_outside_the_api(tmp_path):
    with TestClient(build(tmp_path)) as client:
        preflight = client.options(
            "/api/v1/runs",
            headers={"Origin": ALLOWED_ORIGINS[0], "Access-Control-Request-Method": "PUT"},
        )
    assert preflight.status_code == 400
    assert error_of(preflight)["code"] == "cors_rejected"


# --- static frontend -----------------------------------------------------------------


@pytest.fixture
def dist(tmp_path):
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html><title>Refactor UI</title>", "utf-8")
    (root / "assets" / "app.js").write_text("console.log('ui')", "utf-8")
    (root / "api").mkdir()
    (root / "api" / "secret.json").write_text('{"leak": true}', "utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "index.html").write_text("<p>shadow docs</p>", "utf-8")
    (tmp_path / "outside.txt").write_text("outside the build", "utf-8")
    return root


def test_frontend_is_served_without_shadowing_the_api(tmp_path, dist):
    with TestClient(build(tmp_path, frontend_dist=dist)) as client:
        index = client.get("/")
        assert index.status_code == 200
        assert index.headers["content-type"].startswith("text/html")
        assert "Refactor UI" in index.text
        asset = client.get("/assets/app.js")
        assert asset.status_code == 200 and asset.text == "console.log('ui')"
        assert client.head("/").status_code == 200
        HealthResponse.model_validate(client.get("/health").json())
        RunList.model_validate(client.get("/api/v1/runs").json())
        assert "openapi" in client.get("/openapi.json").json()
        docs = client.get("/docs")
        assert docs.status_code == 200 and "shadow docs" not in docs.text
        reserved = ("/api/v1/nope", "/api/secret.json", "/API/secret.json", "/Docs/index.html")
        for path in (*reserved, "/docs/index.html", "/missing.js", "/assets/"):
            response = client.get(path)
            assert response.status_code == 404, path
            assert error_of(response)["code"] == "not_found"
            assert "leak" not in response.text
        traversal = client.get("/%2e%2e/outside.txt")
        assert traversal.status_code == 404 and "outside the build" not in traversal.text
        assert client.post("/").status_code == 404
        accepted = client.post("/api/v1/runs", json={"code": CODE})
        assert accepted.status_code == 202
        wait_for(client, accepted.json()["run_id"])


def test_frontend_built_after_startup_is_picked_up(tmp_path):
    root = tmp_path / "later"
    with TestClient(build(tmp_path, frontend_dist=root)) as client:
        assert client.get("/").status_code == 404
        root.mkdir()
        (root / "index.html").write_text("<p>built</p>", "utf-8")
        assert client.get("/").text == "<p>built</p>"


# --- health --------------------------------------------------------------------------


class StubLocalProvider:
    def __init__(self, info=None, error=None):
        self._info = info
        self._error = error
        self.closed = 0

    @property
    def mode(self):
        return ProviderMode.LOCAL_MODEL

    def info(self):
        if self._error is not None:
            raise self._error
        return self._info

    def generate(self, request) -> GenerationResult:
        return failed_result(self.mode, "unavailable", "stub")

    def close(self):
        self.closed += 1


def test_health_with_a_local_provider_reports_its_identity(tmp_path):
    home = str(Path.home())
    info = ProviderInfo(
        provider_mode=ProviderMode.LOCAL_MODEL,
        model_id="org/code-model",
        model_revision="a" * 40,
        adapter_id="guard-lora",
        adapter_sha256="b" * 64,
        device="cuda",
        ready=True,
        detail=f"Model loaded from {home}\\models\\code-model",
    )
    provider = StubLocalProvider(info=info)
    with TestClient(build(tmp_path, provider=provider)) as client:
        body = client.get("/health").json()
    assert body["mode"] == "local_model"
    provider_body = body["provider"]
    assert provider_body["model_id"] == "org/code-model"
    assert provider_body["model_revision"] == "a" * 40
    assert (provider_body["adapter_id"], provider_body["adapter_sha256"]) == (
        "guard-lora",
        "b" * 64,
    )
    assert provider_body["ready"] is True
    assert home not in provider_body["detail"] and "~" in provider_body["detail"]
    assert provider.closed == 1  # the lifespan closes the provider


def test_health_survives_a_failing_provider(tmp_path):
    provider = StubLocalProvider(error=RuntimeError("worker pipe broken"))
    with TestClient(build(tmp_path, provider=provider)) as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "local_model"
    assert body["provider"]["ready"] is False
    assert body["provider"]["detail"] == "Provider information is unavailable (RuntimeError)."


class StubRunner:
    def __init__(self, error=None):
        self.error = error

    def info(self):
        if self.error is not None:
            raise self.error
        return RunnerInfo(enabled=True, isolation={"separate_process": True, "no_network": True})

    def run(self, case, candidate_code):
        return ReferenceTestsResult(status="not_run", reason="stub")


def test_health_reports_runner_status(tmp_path):
    with TestClient(build(tmp_path, runner=StubRunner())) as client:
        runner = client.get("/health").json()["runner"]
    assert runner == {
        "enabled": True,
        "reason": None,
        "isolation": {"separate_process": True, "no_network": True},
    }
    with TestClient(build(tmp_path, runner=StubRunner(error=OSError("x")))) as client:
        runner = client.get("/health").json()["runner"]
    assert runner["enabled"] is False
    assert runner["reason"] == "Reference runner information is unavailable (OSError)."


class SlowCheckRunner(StubRunner):
    """info() blocks like the real runner's first isolation self-check."""

    def __init__(self):
        super().__init__()
        self.release = threading.Event()

    def info(self):
        assert self.release.wait(10)
        return super().info()


def test_health_does_not_wait_for_runner_self_checks(tmp_path):
    runner = SlowCheckRunner()
    try:
        with TestClient(build(tmp_path, runner=runner)) as client:
            started = time.monotonic()
            during = client.get("/health").json()["runner"]
            assert time.monotonic() - started < 2.0
            assert during == {"enabled": False, "reason": RUNNER_CHECKS_RUNNING, "isolation": {}}
            runner.release.set()
            deadline = time.monotonic() + 5
            while client.get("/health").json()["runner"]["enabled"] is not True:
                assert time.monotonic() < deadline
                time.sleep(0.01)
    finally:
        runner.release.set()


def test_disabled_runner_setting_overrides_any_runner(tmp_path):
    workflow = ScriptedWorkflow()
    app = create_app(
        settings_for(tmp_path, runner="disabled"),
        workflow=workflow,
        provider=FakeProvider(),
        runner=StubRunner(),
        registry=[CASE],
    )
    with TestClient(app) as client:
        runner = client.get("/health").json()["runner"]
        run_id = client.post("/api/v1/runs", json={"code": CODE}).json()["run_id"]
        wait_for(client, run_id)
    assert runner == {"enabled": False, "reason": RUNNER_DISABLED_REASON, "isolation": {}}
    assert isinstance(workflow.runners_seen[0], DisabledRunner)
    result = workflow.runners_seen[0].run(CASE, CODE)
    assert (result.status, result.case_id, result.reason) == (
        "not_run",
        "demo",
        RUNNER_DISABLED_REASON,
    )


# --- restarts and recovery -----------------------------------------------------------


def test_clean_shutdown_finishes_the_current_run_and_interrupts_the_rest(tmp_path):
    gate = threading.Event()
    workflow = ScriptedWorkflow(gate=gate)
    timer = threading.Timer(0.3, gate.set)
    try:
        with TestClient(build(tmp_path, workflow=workflow)) as client:
            first = client.post("/api/v1/runs", json={"code": CODE}).json()["run_id"]
            assert workflow.entered.wait(5)
            second = client.post("/api/v1/runs", json={"code": CODE}).json()["run_id"]
            timer.start()  # releases the running workflow while shutdown waits for it
    finally:
        timer.cancel()
        gate.set()
    assert len(workflow.calls) == 1
    with TestClient(build(tmp_path)) as client:
        done = client.get(f"/api/v1/runs/{first}").json()
        skipped = client.get(f"/api/v1/runs/{second}").json()
        listed = [run["run_id"] for run in client.get("/api/v1/runs").json()["runs"]]
    assert done["status"] == "completed"
    assert skipped["status"] == "failed"
    assert skipped["error"] == {
        "code": "interrupted",
        "message": NOT_STARTED_MESSAGE,
        "stage": "queued",
    }
    assert listed == [second, first]


def test_restart_after_a_stuck_worker_marks_runs_interrupted(tmp_path):
    gate = threading.Event()
    workflow = ScriptedWorkflow(gate=gate)
    provider = StubLocalProvider(
        info=ProviderInfo(provider_mode=ProviderMode.LOCAL_MODEL, ready=True)
    )
    try:
        app = build(tmp_path, workflow=workflow, provider=provider, shutdown_grace_s=0.2)
        with TestClient(app) as client:
            finished = client.post("/api/v1/runs", json={"code": CODE})
            gate.set()
            wait_for(client, finished.json()["run_id"])
            gate.clear()
            workflow.entered.clear()
            stuck = client.post("/api/v1/runs", json={"code": CODE}).json()["run_id"]
            assert workflow.entered.wait(5)
            waiting = client.post("/api/v1/runs", json={"code": CODE}).json()["run_id"]
            wait_for(client, stuck, statuses=("verifying",))
        # Shutdown gave up after the grace period and closed the provider and the store.
        assert provider.closed == 1
    finally:
        gate.set()  # the stuck worker now finds the store closed and exits
    for thread in threading.enumerate():
        if thread.name == WORKER_THREAD_NAME:
            thread.join(5)
    with TestClient(build(tmp_path)) as client:
        before = client.get(f"/api/v1/runs/{finished.json()['run_id']}").json()
        interrupted = client.get(f"/api/v1/runs/{stuck}").json()
        never_started = client.get(f"/api/v1/runs/{waiting}").json()
        assert len(client.get("/api/v1/runs").json()["runs"]) == 3
        again = client.post("/api/v1/runs", json={"code": CODE}).json()["run_id"]
        assert wait_for(client, again)["status"] == "completed"
    assert before["status"] == "completed"
    assert interrupted["status"] == "failed"
    assert interrupted["error"] == {
        "code": "interrupted",
        "message": INTERRUPTED_MESSAGE,
        "stage": "verifying",
    }
    assert interrupted["started_at"] is not None and interrupted["finished_at"] is not None
    assert interrupted["original_code"] == CODE
    assert never_started["error"]["stage"] == "queued"
    assert never_started["status"] == RunStatus.FAILED


def test_restart_applies_a_lower_retention(tmp_path):
    with TestClient(build(tmp_path, retention=10)) as client:
        ids = []
        for _ in range(4):
            run_id = client.post("/api/v1/runs", json={"code": CODE}).json()["run_id"]
            wait_for(client, run_id)
            ids.append(run_id)
    with TestClient(build(tmp_path, retention=2)) as client:
        listed = [run["run_id"] for run in client.get("/api/v1/runs").json()["runs"]]
    assert listed == [ids[3], ids[2]]
