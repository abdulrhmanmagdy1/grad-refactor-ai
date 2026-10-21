"""Project review API: upload, polling, decisions, patch and download, deletion, limits."""

from __future__ import annotations

import io
import textwrap
import threading
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from refactor_ai.api import create_app
from refactor_ai.config import Settings
from refactor_ai.project.models import ProjectRecord, ProjectStatus
from refactor_ai.project.service import ProjectService, ProjectStore
from refactor_ai.providers.fake import FakeProvider
from refactor_ai.runs.components import DisabledRunner
from refactor_ai.runs.testing import ScriptedWorkflow


def code(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n")


GRADES = code(
    """
    def grade(score):
        if score >= 0:
            if score >= 50:
                return "pass"
            return "fail"
        else:
            raise ValueError("negative score")


    def label(score):
        if score >= 0:
            if score >= 90:
                return "top"
            return "normal"
        else:
            raise ValueError("negative score")
    """
)
TESTS = "from app.grades import grade\n\n\ndef test_grade():\n    assert grade(70) == 'pass'\n"


def project_zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


SAMPLE = project_zip(
    {"app/__init__.py": "", "app/grades.py": GRADES, "tests/test_grades.py": TESTS}
)


@pytest.fixture(autouse=True)
def no_leaked_workers():
    yield
    deadline = time.monotonic() + 10
    for thread in threading.enumerate():
        if thread.name.startswith("refactor-ai-"):
            thread.join(max(0.0, deadline - time.monotonic()))
    assert [t for t in threading.enumerate() if t.name.startswith("refactor-ai-")] == []


@pytest.fixture
def client(tmp_path):
    def build(**settings):
        settings.setdefault("db_path", tmp_path / "data" / "runs.sqlite3")
        settings.setdefault("frontend_dist", None)
        settings.setdefault("shutdown_grace_s", 5.0)
        app = create_app(
            Settings(**settings),
            workflow=ScriptedWorkflow(),
            provider=FakeProvider(),
            runner=DisabledRunner("Disabled in tests."),
            registry=[],
        )
        return TestClient(app)

    return build


def upload(test, data=SAMPLE, **params):
    return test.post(
        "/api/v1/projects", content=data, params=params, headers={"Content-Type": "application/zip"}
    )


def wait_done(test, project_id, timeout=60.0) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        body = test.get(f"/api/v1/projects/{project_id}").json()
        if body["status"] in ("completed", "failed"):
            return body
        assert time.monotonic() < deadline, body["status"]
        time.sleep(0.05)


def test_upload_review_decide_and_download(client, tmp_path):
    with client() as test:
        info = test.get("/api/v1/projects/info").json()
        assert info["uses_model"] is False and info["tests_allowed"] is False
        response = upload(test, name="grades demo")
        assert response.status_code == 202, response.text
        accepted = response.json()
        assert response.headers["Location"] == accepted["poll_url"]
        record = wait_done(test, accepted["project_id"])
        assert record["status"] == "completed" and record["name"] == "grades demo"
        assert record["summary"]["used_model"] is False
        sources = {f["source"] for f in record["findings"]}
        assert "static:task:guard_clauses" in sources and "static:index:no-tests" not in sources
        fixes = {fix["symbol"]: fix for fix in record["fixes"]}
        assert set(fixes) == {"grade", "label"}
        assert all(fix["disposition"] == "uncertain" for fix in fixes.values())

        listed = test.get("/api/v1/projects").json()["projects"]
        assert listed[0]["project_id"] == accepted["project_id"] and "findings" not in listed[0]

        pid = accepted["project_id"]
        assert test.get(f"/api/v1/projects/{pid}/patch").status_code == 409  # nothing accepted
        for symbol, decision in (("grade", "accepted"), ("label", "accepted")):
            response = test.post(
                f"/api/v1/projects/{pid}/fixes/{fixes[symbol]['id']}/decision",
                json={"decision": decision},
            )
            assert response.status_code == 200, response.text
        patch = test.get(f"/api/v1/projects/{pid}/patch")
        assert patch.status_code == 200 and patch.headers["content-type"].startswith("text/x-diff")
        assert patch.text.count("--- a/app/grades.py") == 1
        assert "+    if score < 0:" in patch.text
        download = test.get(f"/api/v1/projects/{pid}/download")
        assert download.status_code == 200
        assert 'filename="grades-demo-reviewed.zip"' in download.headers["content-disposition"]
        with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
            names = set(archive.namelist())
            patched = archive.read("app/grades.py").decode("utf-8")
        assert names == {"app/__init__.py", "app/grades.py", "tests/test_grades.py"}
        assert patched.count("raise ValueError") == 2 and "else:" not in patched
        compile(patched, "grades.py", "exec")  # both accepted fixes applied cleanly

        reject = test.post(
            f"/api/v1/projects/{pid}/fixes/{fixes['label']['id']}/decision",
            json={"decision": "rejected"},
        )
        assert reject.json()["fixes"][1]["decision"] == "rejected"
        assert test.get(f"/api/v1/projects/{pid}/patch").text.count("@@ -") == 1

        assert test.delete(f"/api/v1/projects/{pid}").status_code == 204
        assert test.get(f"/api/v1/projects/{pid}").status_code == 404
        assert not (tmp_path / "data" / "projects" / pid).exists()


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"", "empty"),
        (b"not a zip", "not_a_zip"),
        (project_zip({"README.md": "# docs"}), "no_python_files"),
        (project_zip({"../escape.py": "x = 1\n"}), "unsafe_entry"),
    ],
)
def test_unusable_uploads(client, data, reason):
    with client() as test:
        response = upload(test, data)
        assert response.status_code == 422
        body = response.json()["error"]
        assert body["code"] == "invalid_project" and body["details"] == [{"reason": reason}]
        assert test.get("/api/v1/projects").json()["projects"] == []


def test_upload_size_limit(client):
    with client() as test:
        response = upload(test, b"x" * 5_000_001)
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "payload_too_large"
        assert test.post("/api/v1/runs", content=b"x" * 1_100_000).status_code == 413


def test_unknown_projects_and_fixes(client):
    with client() as test:
        assert test.get("/api/v1/projects/not-an-id").status_code == 404
        assert test.get("/api/v1/projects/" + "a" * 32).json()["error"]["code"] == (
            "project_not_found"
        )
        pid = upload(test).json()["project_id"]
        wait_done(test, pid)
        response = test.post(
            f"/api/v1/projects/{pid}/fixes/X999/decision", json={"decision": "accepted"}
        )
        assert response.status_code == 404 and response.json()["error"]["code"] == "fix_not_found"
        bad = test.post(f"/api/v1/projects/{pid}/fixes/X001/decision", json={"decision": "maybe"})
        assert bad.status_code == 422


def test_project_tests_need_the_server_setting(client):
    with client() as test:
        pid = upload(test, run_tests="true").json()["project_id"]
        record = wait_done(test, pid)
        assert record["run_tests"] is False
        assert any("REFACTOR_AI_PROJECT_TESTS is off" in w for w in record["warnings"])
        assert record["baseline_tests"] is None
    with client(project_tests=True) as test:
        pid = upload(test, run_tests="true").json()["project_id"]
        record = wait_done(test, pid, timeout=120)
        assert record["run_tests"] is True and record["baseline_tests"]["passed"] == 1
        fixes = {fix["symbol"]: fix for fix in record["fixes"]}
        assert fixes["grade"]["tests"]["status"] == "pass"
        assert fixes["grade"]["disposition"] == "proposal_ready"
        assert fixes["label"]["tests"]["status"] == "not_available"  # no test refers to it


def test_unfinished_reviews_are_marked_interrupted_at_start(tmp_path):
    store = ProjectStore(tmp_path / "projects.sqlite3", retention=10)
    store.save(
        ProjectRecord(
            project_id="b" * 32,
            name="left over",
            created_at="2026-10-21T10:00:00Z",
            status=ProjectStatus.REVIEWING,
        )
    )
    service = ProjectService(store, tmp_path / "projects")
    service.start()
    try:
        record = store.get("b" * 32)  # recovered when the service was created
        assert record.status is ProjectStatus.FAILED and record.error["code"] == "interrupted"
    finally:
        assert service.stop(5)
        store.close()


def test_queue_limit_and_retention(tmp_path):
    store = ProjectStore(tmp_path / "projects.sqlite3", retention=1)
    service = ProjectService(store, tmp_path / "projects", max_pending=1)
    first = service.submit(SAMPLE, "one", False)
    from refactor_ai.project.service import ProjectBusy

    with pytest.raises(ProjectBusy):
        service.submit(SAMPLE, "two", False)
    service.start()
    try:
        deadline = time.monotonic() + 60
        while store.get(first.project_id).status is not ProjectStatus.COMPLETED:
            assert time.monotonic() < deadline
            time.sleep(0.05)
        while True:  # the worker frees its slot right after saving the record
            try:
                second = service.submit(SAMPLE, "two", False)
                break
            except ProjectBusy:
                assert time.monotonic() < deadline
                time.sleep(0.02)
        assert store.get(first.project_id) is None  # retention 1: the older finished one went
        assert not (tmp_path / "projects" / first.project_id).exists()
        assert store.get(second.project_id) is not None
    finally:
        assert service.stop(30)
        store.close()
