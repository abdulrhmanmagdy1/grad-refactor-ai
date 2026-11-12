"""Tests for the Markdown run-report export endpoint (FR07 evidence, NFR06)."""

from fastapi.testclient import TestClient

from api.app import app

client = TestClient(app)

LENGTHY_CODE = "def lengthy():\n" + "    y = 2\n" * 35 + "    return y\n"


def _create_run(code: str = LENGTHY_CODE, **extra) -> dict:
    res = client.post("/runs?sync=true", json={"code": code, **extra})
    assert res.status_code == 201
    return res.json()


def test_report_renders_measured_sections():
    run = _create_run()
    res = client.get(f"/runs/{run['id']}/report")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/markdown")
    text = res.text

    # Overview quotes the stored run identity and real execution numbers.
    assert f"`{run['id']}`" in text
    assert "## Findings (static AST analysis)" in text
    assert "long-function" in text
    assert "## Input code" in text
    assert run["input_code"].rstrip() in text
    assert "## Proposed refactoring" in text
    assert run["output_code"].rstrip() in text
    assert "## Diff" in text
    assert "## Verification" in text
    assert "`approved`" in text
    assert "## Metrics (before / after / delta)" in text
    assert "`maintainability_index`" in text
    assert "## Agent trace" in text
    for trace in run["agent_traces"]:
        assert trace["agent"] in text
    assert "## Auto-generated verification tests" in text
    assert "NFR01" in text


def test_report_contains_no_unfilled_placeholders():
    run = _create_run()
    text = client.get(f"/runs/{run['id']}/report").text
    for marker in ("TODO", "FIXME", "XXX", "placeholder"):
        assert marker not in text


def test_report_download_disposition():
    run = _create_run()
    inline = client.get(f"/runs/{run['id']}/report")
    assert inline.headers["content-disposition"].startswith("inline")
    attachment = client.get(f"/runs/{run['id']}/report?download=true")
    assert attachment.headers["content-disposition"].startswith("attachment")
    assert run["id"][:8] in attachment.headers["content-disposition"]


def test_report_not_found():
    res = client.get("/runs/nonexistent-report/report")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_report_reflects_user_decision_and_comment():
    run = _create_run()
    client.post(
        f"/runs/{run['id']}/decision",
        json={"decision": "accepted", "comment": "Ready for the release notes."},
    )
    text = client.get(f"/runs/{run['id']}/report").text
    assert "User decision" in text
    assert "`accepted`" in text
    assert "Ready for the release notes." in text


def test_report_of_failed_run_records_errors_honestly():
    run = _create_run(max_total_tokens=1)
    assert run["status"] == "failed"
    text = client.get(f"/runs/{run['id']}/report").text
    assert "## Errors" in text
    assert "token limit" in text.lower()
    assert "No verification record was stored for this run." in text
    assert "## Verification" in text


def test_report_handles_code_containing_backticks():
    code = "def f():\n    s = '''```'''\n    return s\n"
    run = _create_run(code=code)
    text = client.get(f"/runs/{run['id']}/report").text
    # A fence longer than the embedded run of backticks keeps the block intact.
    assert "````python" in text
