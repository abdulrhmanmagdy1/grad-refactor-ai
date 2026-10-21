"""Run API: submission, polling, history, proposal download, decisions and deletion."""

import json
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from refactor_ai.api import create_app
from refactor_ai.config import Settings
from refactor_ai.contracts import (
    Disposition,
    ReferenceCase,
    ReferenceCaseSummary,
    ReferenceExpectation,
    ReferenceTest,
    RunAccepted,
    RunList,
    RunRecord,
    RunStatus,
)
from refactor_ai.providers.fake import FakeProvider
from refactor_ai.runs.components import DisabledRunner
from refactor_ai.runs.testing import ScriptedWorkflow, scripted_outcome
from refactor_ai.tasks import guard_clauses

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "docs" / "architecture" / "examples"

SHIPPING = '''def shipping_cost(weight, express):
    """Return the shipping cost."""
    if weight > 0:
        if express:
            return weight * 3
        else:
            return weight * 2
    else:
        raise ValueError("weight must be positive")
'''
SHIPPING_CASE = ReferenceCase(
    case_id="shipping_cost",
    task_type="guard_clauses",
    title="Shipping cost",
    function_name="shipping_cost",
    original_code=SHIPPING,
    tests=[
        ReferenceTest(args="[2, True]", expect=ReferenceExpectation(kind="return", value="6")),
        ReferenceTest(
            args="[0, True]", expect=ReferenceExpectation(kind="raise", exception="ValueError")
        ),
    ],
)
TERMINAL = ("completed", "failed")


def example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


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
def make_app(tmp_path):
    def build(*, workflow=None, provider=None, runner=None, registry=None, **settings):
        settings.setdefault("db_path", tmp_path / "data" / "runs.sqlite3")
        settings.setdefault("frontend_dist", None)
        settings.setdefault("shutdown_grace_s", 5.0)
        return create_app(
            Settings(**settings),
            workflow=workflow if workflow is not None else ScriptedWorkflow(),
            provider=provider if provider is not None else FakeProvider(),
            runner=runner if runner is not None else DisabledRunner("Disabled in tests."),
            registry=registry if registry is not None else [SHIPPING_CASE],
        )

    return build


def submit(client, code=SHIPPING, **fields):
    return client.post("/api/v1/runs", json={"code": code, **fields})


def wait_for(client, run_id, statuses=TERMINAL, timeout=10.0) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        response = client.get(f"/api/v1/runs/{run_id}")
        assert response.status_code == 200, response.text
        body = response.json()
        if body["status"] in statuses:
            return body
        if time.monotonic() > deadline:
            raise AssertionError(f"run {run_id} stayed {body['status']}")
        time.sleep(0.01)


def error_code(response) -> str:
    body = response.json()
    assert set(body) == {"error"}, body
    assert set(body["error"]) == {"code", "message", "details"}
    return body["error"]["code"]


# --- submission and polling ----------------------------------------------------------


def test_submit_poll_and_fetch(make_app):
    workflow = ScriptedWorkflow()
    with TestClient(make_app(workflow=workflow)) as client:
        response = submit(client)
        assert response.status_code == 202
        accepted = RunAccepted.model_validate(response.json())
        assert accepted.status == RunStatus.QUEUED
        assert accepted.poll_url == f"/api/v1/runs/{accepted.run_id}"
        assert response.headers["location"] == accepted.poll_url
        assert len(accepted.run_id) == 32 and int(accepted.run_id, 16) >= 0
        body = wait_for(client, accepted.run_id)
        record = RunRecord.model_validate(body)
    assert record.status == RunStatus.COMPLETED
    assert record.original_code == SHIPPING
    assert record.proposed_code == guard_clauses.to_guard_clauses(SHIPPING)
    assert record.provider_mode == "fake"
    assert record.settings.mode == "multi_role"
    assert record.verification.disposition == Disposition.PROPOSAL_READY
    assert record.started_at is not None and record.finished_at is not None
    assert workflow.calls[0].reference_case is None


def test_single_role_mode_is_passed_to_the_workflow(make_app):
    workflow = ScriptedWorkflow()
    with TestClient(make_app(workflow=workflow)) as client:
        run_id = submit(client, workflow_mode="single_role").json()["run_id"]
        body = wait_for(client, run_id)
    assert body["workflow_mode"] == "single_role"
    assert body["settings"]["mode"] == "single_role"
    assert workflow.settings_seen[0].mode == "single_role"


def test_line_endings_are_normalized_before_storage(make_app):
    workflow = ScriptedWorkflow()
    with TestClient(make_app(workflow=workflow)) as client:
        run_id = submit(client, code=SHIPPING.replace("\n", "\r\n")).json()["run_id"]
        body = wait_for(client, run_id)
    assert body["original_code"] == SHIPPING
    assert workflow.calls[0].code == SHIPPING


@pytest.mark.parametrize(
    "payload",
    [
        {"code": ""},
        {"code": "   \n\t  "},
        {},
        {"code": 123},
        {"code": None},
        {"code": SHIPPING, "unexpected": True},
        {"code": SHIPPING, "task_type": "rename_variable"},
        {"code": SHIPPING, "workflow_mode": "solo"},
        {"code": SHIPPING, "reference_case_id": "../etc/passwd"},
        {"code": SHIPPING, "reference_case_id": "Shipping"},
        {"code": SHIPPING, "reference_case_id": ""},
    ],
)
def test_invalid_requests_are_validation_errors(make_app, payload):
    with TestClient(make_app()) as client:
        response = client.post("/api/v1/runs", json=payload)
        assert response.status_code == 422
        assert error_code(response) == "validation_error"
        assert response.json()["error"]["details"]
        assert client.get("/api/v1/runs").json()["runs"] == []


@pytest.mark.parametrize(
    ("content", "content_type"),
    [
        (b"not json", "application/json"),
        (b'{"code": "x"', "application/json"),
        (b"", "application/json"),
        (b'["def f(): pass"]', "application/json"),
        (b'{"code": "def f():\\n    return 1\\n"}', "text/plain"),
    ],
)
def test_malformed_bodies_are_validation_errors(make_app, content, content_type):
    with TestClient(make_app()) as client:
        response = client.post(
            "/api/v1/runs", content=content, headers={"content-type": content_type}
        )
        assert response.status_code == 422
        assert error_code(response) == "validation_error"
        assert response.json()["error"]["message"].startswith("Invalid request (body): ")


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b'{"code": "\xff"}', "the body is not valid UTF-8"),
        (b"[" * 100_000, "the JSON is nested too deeply"),
    ],
    ids=["invalid-utf8", "deep-nesting"],
)
@pytest.mark.parametrize("path", ["/api/v1/runs", "/api/v1/analyze"])
def test_undecodable_bodies_are_validation_errors(make_app, content, reason, path):
    """FastAPI answers these with a bare 400; the error contract lists malformed JSON
    under 422 validation_error."""
    with TestClient(make_app()) as client:
        response = client.post(path, content=content, headers={"content-type": "application/json"})
        assert response.status_code == 422, response.text
        error = response.json()["error"]
        assert error_code(response) == "validation_error"
        assert error["message"] == f"Invalid request (body): JSON decode error ({reason})"
        assert error["details"] == [
            {"loc": ["body"], "message": f"JSON decode error ({reason})", "type": "json_invalid"}
        ]
        assert client.get("/api/v1/runs").json()["runs"] == []


def test_blank_code_error_matches_the_published_example(make_app):
    with TestClient(make_app()) as client:
        response = submit(client, code="   ")
    assert response.json() == example("error_validation_error.json")


def test_input_limit_is_20000_characters(make_app):
    with TestClient(make_app()) as client:
        accepted = submit(client, code="#" * 20000)
        assert accepted.status_code == 202
        wait_for(client, accepted.json()["run_id"])
        rejected = submit(client, code="#" * 20001)
        assert rejected.status_code == 422
        assert error_code(rejected) == "validation_error"
        assert "#" * 100 not in rejected.text  # the input is never echoed back
        assert len(client.get("/api/v1/runs").json()["runs"]) == 1


@pytest.mark.parametrize(
    "code",
    [
        "def f(:\n    pass\n",
        "def f():\n    return 1\n  return 2\n",
        "x = 1\x00\n",
        "(" * 10000 + ")" * 10000,
        "-" * 19999 + "1",
        "+".join(["1"] * 9000),
        "not " * 4999 + "x",
    ],
    ids=["syntax", "indentation", "null-byte", "parentheses", "unary", "binary", "not-chain"],
)
def test_unparseable_code_is_invalid_syntax(make_app, code):
    workflow = ScriptedWorkflow()
    with TestClient(make_app(workflow=workflow)) as client:
        response = submit(client, code=code)
        assert response.status_code == 422
        assert error_code(response) == "invalid_syntax"
        (detail,) = response.json()["error"]["details"]
        assert set(detail) == {"line", "column", "message"}
        assert client.get("/api/v1/runs").json()["runs"] == []
    assert workflow.calls == []


def test_invalid_syntax_reports_the_location(make_app):
    with TestClient(make_app()) as client:
        response = submit(client, code="def shipping_cost(weight express):\n    return weight\n")
    assert response.json() == example("error_invalid_syntax.json")
    assert response.json()["error"]["details"][0]["line"] == 1


# --- reference cases -----------------------------------------------------------------


def test_reference_cases_are_listed_as_summaries(make_app):
    with TestClient(make_app()) as client:
        response = client.get("/api/v1/reference-cases")
    assert response.status_code == 200
    (summary,) = [ReferenceCaseSummary.model_validate(item) for item in response.json()]
    assert summary.case_id == "shipping_cost"
    assert summary.code == SHIPPING
    assert summary.test_count == 2
    assert summary.function_name == "shipping_cost"


def test_reference_case_run_passes_the_trusted_case(make_app):
    workflow = ScriptedWorkflow()
    with TestClient(make_app(workflow=workflow)) as client:
        exact = submit(client, reference_case_id="shipping_cost")
        assert exact.status_code == 202
        crlf = submit(
            client,
            code=SHIPPING.replace("\n", "\r\n") + "\r\n\r\n",
            reference_case_id="shipping_cost",
        )
        assert crlf.status_code == 202
        for response in (exact, crlf):
            body = wait_for(client, response.json()["run_id"])
            assert body["reference_case_id"] == "shipping_cost"
    assert [call.reference_case for call in workflow.calls] == [SHIPPING_CASE, SHIPPING_CASE]


def test_reference_case_mismatch_and_unknown_case(make_app):
    workflow = ScriptedWorkflow()
    with TestClient(make_app(workflow=workflow)) as client:
        changed = SHIPPING.replace("weight * 3", "weight * 4")
        mismatch = submit(client, code=changed, reference_case_id="shipping_cost")
        assert mismatch.status_code == 422
        assert mismatch.json() == example("error_reference_case_mismatch.json")
        unknown = submit(client, reference_case_id="missing_case")
        assert unknown.status_code == 422
        assert unknown.json() == example("error_unknown_reference_case.json")
        assert client.get("/api/v1/runs").json()["runs"] == []
    assert workflow.calls == []


# --- queue ---------------------------------------------------------------------------


def test_full_queue_returns_busy_with_retry_after(make_app):
    gate = threading.Event()
    workflow = ScriptedWorkflow(gate=gate)
    try:
        with TestClient(make_app(workflow=workflow, max_pending=4)) as client:
            accepted = [submit(client) for _ in range(4)]
            assert [r.status_code for r in accepted] == [202] * 4
            assert client.get("/health").json()["queue"] == {"max_pending": 4, "pending": 4}
            busy = submit(client)
            assert busy.status_code == 503
            assert busy.headers["retry-after"] == "10"
            assert busy.json() == example("error_busy.json")
            assert len(client.get("/api/v1/runs").json()["runs"]) == 4
            gate.set()
            for response in accepted:
                assert wait_for(client, response.json()["run_id"])["status"] == "completed"
            deadline = time.monotonic() + 5
            while client.get("/health").json()["queue"]["pending"]:
                assert time.monotonic() < deadline
                time.sleep(0.01)
            again = submit(client)
            assert again.status_code == 202
            wait_for(client, again.json()["run_id"])
    finally:
        gate.set()


def test_workflow_calls_are_serialized(make_app):
    workflow = ScriptedWorkflow(delay_s=0.02)
    with TestClient(make_app(workflow=workflow, max_pending=5)) as client:
        ids = [submit(client).json()["run_id"] for _ in range(5)]
        for run_id in ids:
            assert wait_for(client, run_id)["status"] == "completed"
    assert workflow.max_active == 1
    assert len(workflow.calls) == 5


def test_status_progress_is_visible_while_running(make_app):
    gate = threading.Event()
    workflow = ScriptedWorkflow(
        statuses=[RunStatus.ANALYZING, RunStatus.GENERATING, RunStatus.COMPLETED], gate=gate
    )
    try:
        with TestClient(make_app(workflow=workflow)) as client:
            run_id = submit(client).json()["run_id"]
            body = wait_for(client, run_id, statuses=("generating",))
            assert body["started_at"] is not None and body["finished_at"] is None
            assert body["proposed_code"] is None
            summary = client.get("/api/v1/runs").json()["runs"][0]
            assert (summary["status"], summary["disposition"]) == ("generating", None)
            gate.set()
            assert wait_for(client, run_id)["status"] == "completed"
    finally:
        gate.set()


def test_workflow_exception_is_a_failed_run_without_internals(make_app):
    workflow = ScriptedWorkflow(
        statuses=[RunStatus.ANALYZING], error=ValueError("leaked detail C:\\Users\\x\\key.txt")
    )
    with TestClient(make_app(workflow=workflow)) as client:
        run_id = submit(client).json()["run_id"]
        body = wait_for(client, run_id)
        response = client.get(f"/api/v1/runs/{run_id}")
        listed = client.get("/api/v1/runs").json()["runs"][0]
    assert body["status"] == "failed"
    assert body["error"]["code"] == "internal_error"
    assert body["error"]["stage"] == "analyzing"
    assert "leaked detail" not in response.text
    assert "key.txt" not in response.text
    assert "Traceback" not in response.text
    assert listed["disposition"] == "failed"


def test_missing_coordinator_fails_runs_clearly(make_app, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "refactor_ai.agents.coordinator", None)
    app = create_app(
        Settings(db_path=tmp_path / "runs.sqlite3", frontend_dist=None, runner="disabled"),
        provider=FakeProvider(),
        registry=[],
    )
    with TestClient(app) as client:
        run_id = submit(client).json()["run_id"]
        body = wait_for(client, run_id)
    assert body["status"] == "failed"
    assert body["error"]["code"] == "workflow_unavailable"
    assert "not available" in body["error"]["message"]


# --- history -------------------------------------------------------------------------


def test_run_list_is_newest_first_and_bounded(make_app):
    with TestClient(make_app(max_pending=5)) as client:
        ids = [submit(client).json()["run_id"] for _ in range(3)]
        for run_id in ids:
            wait_for(client, run_id)
        listed = RunList.model_validate(client.get("/api/v1/runs").json())
        assert listed.limit == 20
        assert [run.run_id for run in listed.runs] == list(reversed(ids))
        assert all(run.disposition == Disposition.PROPOSAL_READY for run in listed.runs)
        two = client.get("/api/v1/runs", params={"limit": 2}).json()
        assert [run["run_id"] for run in two["runs"]] == list(reversed(ids))[:2]
        assert two["limit"] == 2
        assert client.get("/api/v1/runs", params={"limit": 50}).status_code == 200
        for bad in ("0", "51", "-1", "abc", "2.5"):
            response = client.get("/api/v1/runs", params={"limit": bad})
            assert response.status_code == 422, bad
            assert error_code(response) == "validation_error"


@pytest.mark.parametrize(
    "run_id",
    ["0" * 32, "abc", "A" * 32, "g" * 32, "a" * 33, "a" * 31, "..%2F..%2Fsecret"],
)
def test_unknown_or_malformed_run_ids_are_not_found(make_app, run_id):
    with TestClient(make_app()) as client:
        for method, path in (
            ("GET", f"/api/v1/runs/{run_id}"),
            ("GET", f"/api/v1/runs/{run_id}/proposal"),
            ("DELETE", f"/api/v1/runs/{run_id}"),
        ):
            response = client.request(method, path)
            assert response.status_code == 404, (method, path)
            assert error_code(response) in ("run_not_found", "not_found")
        response = client.post(f"/api/v1/runs/{run_id}/decision", json={"decision": "accepted"})
        assert response.status_code == 404


def test_run_not_found_matches_the_published_example(make_app):
    with TestClient(make_app()) as client:
        response = client.get(f"/api/v1/runs/{'0' * 32}")
    assert response.json() == example("error_run_not_found.json")


# --- proposal download and decisions -------------------------------------------------


def test_proposal_download_is_a_safe_attachment(make_app, tmp_path):
    with TestClient(make_app()) as client:
        run_id = submit(client).json()["run_id"]
        body = wait_for(client, run_id)
        before = sorted(p.name for p in tmp_path.rglob("*") if p.suffix == ".py")
        response = client.get(f"/api/v1/runs/{run_id}/proposal")
    assert response.status_code == 200
    assert response.content == body["proposed_code"].encode("utf-8")
    assert response.headers["content-type"] == "text/x-python; charset=utf-8"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="proposal-{run_id}.py"'
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
    # Nothing is written on the host: the proposal only travels in the response.
    assert sorted(p.name for p in tmp_path.rglob("*") if p.suffix == ".py") == before == []


def test_proposal_unavailable_until_finished_and_without_code(make_app):
    gate = threading.Event()
    no_change = ScriptedWorkflow(
        statuses=[],
        outcome=lambda r, p, s: scripted_outcome(r, p, s, Disposition.NO_CHANGE),
        gate=gate,
    )
    try:
        with TestClient(make_app(workflow=no_change)) as client:
            run_id = submit(client).json()["run_id"]
            running = client.get(f"/api/v1/runs/{run_id}/proposal")
            assert running.status_code == 409
            assert error_code(running) == "proposal_unavailable"
            assert "not finished" in running.json()["error"]["message"]
            gate.set()
            assert wait_for(client, run_id)["verification"]["disposition"] == "no_change"
            finished = client.get(f"/api/v1/runs/{run_id}/proposal")
            assert finished.status_code == 409
            assert finished.json() == example("error_proposal_unavailable.json")
    finally:
        gate.set()


def test_failed_run_has_no_proposal(make_app):
    workflow = ScriptedWorkflow(error=RuntimeError("boom"))
    with TestClient(make_app(workflow=workflow)) as client:
        run_id = submit(client).json()["run_id"]
        wait_for(client, run_id)
        assert client.get(f"/api/v1/runs/{run_id}/proposal").status_code == 409
        decision = client.post(f"/api/v1/runs/{run_id}/decision", json={"decision": "accepted"})
        assert decision.status_code == 409
        assert error_code(decision) == "proposal_unavailable"


@pytest.mark.parametrize("disposition", [Disposition.UNCERTAIN, Disposition.REJECTED])
def test_any_completed_proposal_can_be_downloaded_and_decided(make_app, disposition):
    workflow = ScriptedWorkflow(outcome=lambda r, p, s: scripted_outcome(r, p, s, disposition))
    with TestClient(make_app(workflow=workflow)) as client:
        run_id = submit(client).json()["run_id"]
        assert wait_for(client, run_id)["verification"]["disposition"] == disposition
        assert client.get(f"/api/v1/runs/{run_id}/proposal").status_code == 200
        response = client.post(f"/api/v1/runs/{run_id}/decision", json={"decision": "rejected"})
        assert response.status_code == 200


def test_decisions_are_recorded_and_can_change(make_app):
    with TestClient(make_app()) as client:
        run_id = submit(client).json()["run_id"]
        wait_for(client, run_id)
        accepted = client.post(f"/api/v1/runs/{run_id}/decision", json={"decision": "accepted"})
        assert accepted.status_code == 200
        assert RunRecord.model_validate(accepted.json()).human_decision == "accepted"
        assert client.get(f"/api/v1/runs/{run_id}").json()["human_decision"] == "accepted"
        rejected = client.post(f"/api/v1/runs/{run_id}/decision", json={"decision": "rejected"})
        assert rejected.json()["human_decision"] == "rejected"
        assert client.get("/api/v1/runs").json()["runs"][0]["human_decision"] == "rejected"
        for payload in ({"decision": "maybe"}, {}, {"decision": "accepted", "x": 1}):
            response = client.post(f"/api/v1/runs/{run_id}/decision", json=payload)
            assert response.status_code == 422
            assert error_code(response) == "validation_error"
        assert client.get(f"/api/v1/runs/{run_id}").json()["human_decision"] == "rejected"


def test_decision_before_the_run_finishes_is_refused(make_app):
    gate = threading.Event()
    try:
        with TestClient(make_app(workflow=ScriptedWorkflow(gate=gate))) as client:
            run_id = submit(client).json()["run_id"]
            response = client.post(f"/api/v1/runs/{run_id}/decision", json={"decision": "accepted"})
            assert response.status_code == 409
            assert error_code(response) == "proposal_unavailable"
            gate.set()
            wait_for(client, run_id)
            assert client.get(f"/api/v1/runs/{run_id}").json()["human_decision"] is None
    finally:
        gate.set()


# --- deletion ------------------------------------------------------------------------


def test_delete_removes_the_record(make_app):
    with TestClient(make_app()) as client:
        run_id = submit(client).json()["run_id"]
        wait_for(client, run_id)
        response = client.delete(f"/api/v1/runs/{run_id}")
        assert response.status_code == 204
        assert response.content == b""
        assert client.get(f"/api/v1/runs/{run_id}").status_code == 404
        assert client.delete(f"/api/v1/runs/{run_id}").status_code == 404
        assert client.get("/api/v1/runs").json()["runs"] == []


def test_deleting_a_waiting_run_skips_it(make_app):
    gate = threading.Event()
    workflow = ScriptedWorkflow(gate=gate)
    try:
        with TestClient(make_app(workflow=workflow)) as client:
            first = submit(client).json()["run_id"]
            assert workflow.entered.wait(5)
            second = submit(client).json()["run_id"]
            assert client.delete(f"/api/v1/runs/{second}").status_code == 204
            gate.set()
            wait_for(client, first)
            deadline = time.monotonic() + 5
            while client.get("/health").json()["queue"]["pending"]:
                assert time.monotonic() < deadline
                time.sleep(0.01)
            assert [run["run_id"] for run in client.get("/api/v1/runs").json()["runs"]] == [first]
    finally:
        gate.set()
    assert len(workflow.calls) == 1


def test_retention_keeps_the_newest_runs(make_app):
    with TestClient(make_app(retention=2, max_pending=1)) as client:
        ids = []
        for _ in range(4):
            run_id = submit(client).json()["run_id"]
            wait_for(client, run_id)
            ids.append(run_id)
        listed = [run["run_id"] for run in client.get("/api/v1/runs").json()["runs"]]
        assert listed == [ids[3], ids[2]]
        assert client.get(f"/api/v1/runs/{ids[0]}").status_code == 404


# --- NFR01: the API never executes submitted or generated code -----------------------


def _file_writing_snippets(target: Path) -> list[str]:
    path = repr(str(target))
    return [
        f"from pathlib import Path\nPath({path}).write_text('executed')\n",
        f"open({path}, 'w').write('executed')\n",
        (
            "def leak(flag):\n"
            "    if flag:\n"
            f"        open({path}, 'w').write('executed')\n"
            "        return 1\n"
            "    else:\n"
            "        return 0\n"
        ),
        (
            "def shipping_cost(weight, express):\n"
            "    if weight > 0:\n"
            "        if express:\n"
            f"            return __import__('pathlib').Path({path}).write_text('x')\n"
            "        else:\n"
            "            return weight * 2\n"
            "    else:\n"
            "        raise ValueError('weight must be positive')\n"
        ),
    ]


def test_runs_never_execute_submitted_or_generated_code(make_app, tmp_path):
    target = tmp_path / "must-not-exist"
    with TestClient(make_app(max_pending=4)) as client:
        ids = []
        for code in _file_writing_snippets(target):
            response = submit(client, code=code)
            assert response.status_code == 202
            ids.append(response.json()["run_id"])
        for run_id in ids:
            body = wait_for(client, run_id)
            assert body["status"] == "completed"
            assert client.get(f"/api/v1/runs/{run_id}/proposal").status_code == 200
        analyzed = client.post("/api/v1/analyze", json={"code": _file_writing_snippets(target)[0]})
        assert analyzed.status_code == 200
    assert not target.exists()


def test_real_coordinator_with_fake_provider_does_not_execute_code(tmp_path):
    pytest.importorskip("refactor_ai.agents.coordinator")
    target = tmp_path / "must-not-exist"
    app = create_app(
        Settings(db_path=tmp_path / "runs.sqlite3", frontend_dist=None, runner="disabled"),
        provider=FakeProvider(),
        registry=[],
    )
    with TestClient(app) as client:
        ids = [
            submit(client, code=code).json()["run_id"] for code in _file_writing_snippets(target)
        ]
        for run_id in ids:
            assert wait_for(client, run_id, timeout=30)["status"] in TERMINAL
    assert not target.exists()


def test_real_coordinator_end_to_end_with_fake_provider(tmp_path):
    """Integration with refactor_ai.agents.coordinator; asserts contract invariants only."""
    pytest.importorskip("refactor_ai.agents.coordinator")
    app = create_app(
        Settings(db_path=tmp_path / "runs.sqlite3", frontend_dist=None, runner="disabled"),
        provider=FakeProvider(),
        registry=[SHIPPING_CASE],
    )
    unsupported = "def sign(x):\n    if x > 0:\n        return 1\n    return 0\n"
    with TestClient(app) as client:
        ids = {
            "case": submit(client, reference_case_id="shipping_cost").json()["run_id"],
            "single": submit(client, workflow_mode="single_role").json()["run_id"],
            "unsupported": submit(client, code=unsupported).json()["run_id"],
        }
        records = {
            name: RunRecord.model_validate(wait_for(client, rid, timeout=60))
            for name, rid in ids.items()
        }
        downloads = {
            name: client.get(f"/api/v1/runs/{rid}/proposal").status_code
            for name, rid in ids.items()
        }
    for name, record in records.items():
        assert record.status == RunStatus.COMPLETED, (name, record.error)
        assert record.provider_mode == "fake"
        assert record.call_count <= record.settings.max_calls
        assert record.verification is not None
        tests = record.verification.reference_tests.status
        assert tests != "pass"  # the runner is disabled, so nothing can pass
        # Missing reference tests never count as a pass.
        assert record.verification.disposition != Disposition.PROPOSAL_READY
        if record.explanation:
            assert record.explanation.startswith("FAKE PROVIDER (not a model):")
    assert records["case"].verification.reference_tests.status == "not_run"
    assert records["single"].settings.mode == "single_role"
    assert records["unsupported"].verification.disposition == Disposition.NO_CHANGE
    assert records["unsupported"].call_count == 0
    assert downloads["unsupported"] == 409
    assert downloads["case"] == (200 if records["case"].proposed_code else 409)


def test_default_wiring_runs_a_real_demo_case_end_to_end(tmp_path):
    """The default lazy wiring (real coordinator and the real demonstration cases) with
    FakeProvider; the runner is disabled so the test stays fast and executes nothing."""
    pytest.importorskip("refactor_ai.agents.coordinator")
    from refactor_ai.runs.components import DEMO_CASES_PATH

    if not DEMO_CASES_PATH.is_file():
        pytest.skip("src/refactor_ai/fixtures/demo_cases.json is not written yet")
    app = create_app(
        Settings(db_path=tmp_path / "runs.sqlite3", frontend_dist=None, runner="disabled"),
        provider=FakeProvider(),
    )
    with TestClient(app) as client:
        cases = client.get("/api/v1/reference-cases")
        assert cases.status_code == 200
        summaries = [ReferenceCaseSummary.model_validate(item) for item in cases.json()]
        assert summaries, "the demonstration allowlist is empty"
        case = summaries[0]
        response = submit(client, code=case.code, reference_case_id=case.case_id)
        assert response.status_code == 202
        record = RunRecord.model_validate(wait_for(client, response.json()["run_id"], timeout=60))
    assert record.status == RunStatus.COMPLETED, record.error
    assert record.reference_case_id == case.case_id
    assert record.provider_mode == "fake"
    assert record.verification is not None
    assert record.verification.reference_tests.status != "pass"
    assert record.verification.disposition != Disposition.PROPOSAL_READY
