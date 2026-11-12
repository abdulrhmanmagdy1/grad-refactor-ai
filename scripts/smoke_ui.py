"""Release smoke test: prove the whole product boots and serves, in one command.

The script drives the real ASGI application in-process (no network port needed)
against a throwaway SQLite database, so it never touches the developer's run
history:

1. ``/health`` answers
2. the built web client is served at ``/`` and every asset it references exists
3. the security headers are present
4. a mock-provider run completes end to end with a diff and passing tests
5. the run report renders as Markdown
6. the measured aggregates and the Prometheus exposition answer

Usage:
    python scripts/smoke_ui.py
"""

import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend" / "dist"

sys.path.insert(0, str(ROOT / "src"))

# Keep the smoke output readable: the service logs are not part of the result.
os.environ.setdefault("REFACTOR_AI_LOG_LEVEL", "WARNING")
os.environ.setdefault("REFACTOR_AI_LOG_FORMAT", "text")

CODE = '''def route_order(order):
    """Decide how an order should be handled."""
    if order["total"] > 100:
        if order["customer"]["vip"]:
            if order["paid"]:
                if order["fast"]:
                    return "vip-fast-paid"
                return "vip-paid"
    return "review"
'''

TESTS = """from solution import route_order


def test_fast_vip():
    order = {"total": 200, "paid": True, "fast": True, "customer": {"vip": True}}
    assert route_order(order) == "vip-fast-paid"


def test_review():
    order = {"total": 10, "paid": False, "fast": False, "customer": {"vip": False}}
    assert route_order(order) == "review"
"""


def _fail(problems: list[str]) -> None:
    print("Smoke test FAILED:\n")
    for problem in problems:
        print(f"  - {problem}")
    raise SystemExit(1)


def main() -> None:
    if not (DIST / "index.html").exists():
        print(
            "The web client bundle is missing (frontend/dist/index.html).\n"
            "Build it first:  cd frontend && npm ci && npm run build"
        )
        raise SystemExit(2)

    from fastapi.testclient import TestClient

    from agents.orchestrator import WorkflowOrchestrator
    from api.app import app
    from api.dependencies import get_db, get_orchestrator
    from core.db import DatabaseManager
    from models.mock_provider import MockModelProvider

    problems: list[str] = []
    checks: list[str] = []

    with tempfile.TemporaryDirectory() as temp_dir:
        database = DatabaseManager(Path(temp_dir) / "smoke.sqlite3")
        smoke_orchestrator = WorkflowOrchestrator(
            database=database,
            default_provider=MockModelProvider(),
            max_retries=1,
        )
        app.dependency_overrides[get_db] = lambda: database
        app.dependency_overrides[get_orchestrator] = lambda: smoke_orchestrator

        try:
            with TestClient(app) as client:
                # 1. Health
                health = client.get("/health")
                if health.status_code != 200 or health.json().get("status") != "ok":
                    problems.append(f"/health returned {health.status_code}: {health.text[:160]}")
                else:
                    checks.append("health endpoint")

                # 2. The built client is served, and its assets exist
                index = client.get("/")
                if index.status_code != 200 or '<div id="root">' not in index.text:
                    problems.append("/ did not serve the built web client")
                else:
                    checks.append("web client at /")
                    for asset in re.findall(r'(?:src|href)="(/assets/[^"]+)"', index.text):
                        if not Path(DIST, asset.lstrip("/")).exists():
                            problems.append(f"index.html references a missing asset: {asset}")
                    checks.append("hashed assets present")

                # 3. Security headers
                csp = index.headers.get("content-security-policy", "")
                if "default-src 'self'" not in csp:
                    problems.append("the Content-Security-Policy header is missing on /")
                elif index.headers.get("x-content-type-options") != "nosniff":
                    problems.append("x-content-type-options is not nosniff")
                else:
                    checks.append("security headers")

                # 4. An end-to-end run
                created = client.post(
                    "/runs?sync=true",
                    json={
                        "code": CODE,
                        "test_code": TESTS,
                        "provider": "mock",
                        "refactoring_type": "deep-nesting",
                    },
                )
                if created.status_code != 201:
                    detail = created.text[:200]
                    problems.append(f"POST /runs returned {created.status_code}: {detail}")
                    payload: dict = {}
                else:
                    payload = created.json()
                    status = payload.get("status")
                    if status != "completed":
                        problems.append(f"the run finished as {status!r}, not completed")
                    elif not payload.get("diff"):
                        problems.append("the run produced no diff")
                    elif not (payload.get("verification") or {}).get("tests_passed"):
                        problems.append("the sandbox reported the tests as failing")
                    else:
                        checks.append("end-to-end run (approved, diff, tests pass)")

                # 5. Markdown report
                if payload.get("id"):
                    report = client.get(f"/runs/{payload['id']}/report")
                    if report.status_code != 200 or "#" not in report.text:
                        problems.append(f"/runs/{{id}}/report returned {report.status_code}")
                    else:
                        checks.append("Markdown report")

                # 6. Operational surface
                stats = client.get("/api/v1/stats")
                if stats.status_code != 200 or stats.json().get("total_runs") != 1:
                    detail = stats.text[:160]
                    problems.append(f"/api/v1/stats returned {stats.status_code}: {detail}")
                else:
                    checks.append("measured aggregates")

                metrics = client.get("/metrics")
                if metrics.status_code != 200 or "refactor_runs_total" not in metrics.text:
                    problems.append(f"/metrics returned {metrics.status_code}")
                else:
                    checks.append("Prometheus metrics")
        finally:
            app.dependency_overrides.clear()

    if problems:
        _fail(problems)

    print(f"Smoke test passed: {len(checks)} checks")
    for check in checks:
        print(f"  [ok] {check}")


if __name__ == "__main__":
    main()
