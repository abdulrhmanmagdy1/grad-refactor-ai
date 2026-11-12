"""Regression test for the asynchronous run path (FR03, FR07).

The async route inserts the queued record and the background worker then
executes the workflow with the same identifier. The store must upsert instead
of failing with a duplicate key, otherwise the run stays ``queued`` forever.
"""

import time

from fastapi.testclient import TestClient

from api.app import app

client = TestClient(app)

CODE = "def lengthy():\n" + "    y = 2\n" * 35 + "    return y\n"


def test_async_run_progresses_to_a_terminal_state():
    created = client.post("/runs", json={"code": CODE, "provider": "mock"})
    assert created.status_code == 201
    run_id = created.json()["id"]
    assert created.json()["status"] == "queued"

    deadline = time.monotonic() + 60
    record = created.json()
    while time.monotonic() < deadline:
        fetched = client.get(f"/runs/{run_id}")
        assert fetched.status_code == 200
        record = fetched.json()
        if record["status"] in {"completed", "failed"}:
            break
        time.sleep(0.4)

    assert record["status"] in {"completed", "failed"}
    assert record["status"] != "queued", "the background worker never executed the run"
    assert record["verification"] is not None
    assert record["agent_traces"], "the executed run must record its agent trace"
