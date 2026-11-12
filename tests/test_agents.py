"""Unit and integration tests for Multi-Agent coordination pipeline
(FR03, FR04, FR07, FR08, ADR10).
"""

import pytest

from agents.orchestrator import WorkflowOrchestrator
from core.db import DatabaseManager
from core.schemas import CreateRunRequest, RunStatus
from models.mock_provider import MockModelProvider


@pytest.fixture
def memory_db():
    return DatabaseManager(db_path=":memory:")


class NoOpProvider(MockModelProvider):
    """Return the original module unchanged to exercise no-op rejection."""

    async def generate_refactoring(self, code, findings, options=None):
        return code, {"provider": "noop", "total_tokens": 1}


@pytest.mark.anyio
async def test_rejects_ast_identical_no_op(memory_db):
    orch = WorkflowOrchestrator(
        database=memory_db,
        default_provider=NoOpProvider(),
        max_retries=0,
    )
    code = (
        "def nested(x):\n"
        "    if x:\n"
        "        if x > 1:\n"
        "            if x > 2:\n"
        "                if x > 3:\n"
        "                    return x\n"
        "    return 0\n"
    )

    run = await orch.execute_run(CreateRunRequest(code=code))

    assert run.status == RunStatus.FAILED
    assert run.verification is not None
    assert run.verification.review_verdict == "rejected"
    assert "AST-identical" in run.verification.review_notes


@pytest.mark.anyio
async def test_orchestrator_successful_flow(memory_db):
    provider = MockModelProvider()
    orch = WorkflowOrchestrator(database=memory_db, default_provider=provider)

    code = "def large_handler():\n" + "    x = 1\n" * 35 + "    return x\n"
    req = CreateRunRequest(code=code)

    run = await orch.execute_run(req)

    assert run.status == RunStatus.COMPLETED
    assert run.output_code is not None
    assert "_large_handler_chunk" in run.output_code
    assert run.diff is not None
    assert run.verification is not None
    assert run.verification.syntax_valid is True
    assert run.verification.review_verdict == "approved"
    assert run.metrics["retries_used"] == 0

    # Verify run was saved in db
    fetched = memory_db.get_run(run.id)
    assert fetched is not None
    assert fetched.status == RunStatus.COMPLETED


@pytest.mark.anyio
async def test_bounded_correction_loop_success_on_retry(memory_db):
    # Provider fails on first attempt with syntax error, succeeds on retry
    provider = MockModelProvider(fail_on_first_try=True)
    orch = WorkflowOrchestrator(database=memory_db, default_provider=provider, max_retries=1)

    code = (
        "def deeply_nested(x):\n"
        "    if x:\n"
        "        if x > 1:\n"
        "            if x > 2:\n"
        "                return x\n"
    )
    req = CreateRunRequest(code=code)

    run = await orch.execute_run(req)

    # Should recover on the single retry and complete
    assert run.status == RunStatus.COMPLETED
    assert run.metrics["retries_used"] == 1
    assert "generation_attempt_2_ms" in run.metrics
    assert run.verification.review_verdict == "approved"


@pytest.mark.anyio
async def test_bounded_correction_loop_exhaustion(memory_db):
    # Provider always fails
    provider = MockModelProvider(always_fail=True)
    orch = WorkflowOrchestrator(database=memory_db, default_provider=provider, max_retries=1)

    code = "def task(x): return x"
    req = CreateRunRequest(code=code)

    run = await orch.execute_run(req)

    # Should fail after exactly 1 retry
    assert run.status == RunStatus.FAILED
    assert run.metrics["retries_used"] == 1
    assert run.verification.review_verdict == "rejected"
    assert "invalid Python syntax" in run.errors


@pytest.mark.anyio
async def test_rejects_malformed_input_immediately(memory_db):
    orch = WorkflowOrchestrator(database=memory_db)
    req = CreateRunRequest(code="def broken_syntax(:\n    pass")

    run = await orch.execute_run(req)
    assert run.status == RunStatus.FAILED
    assert "SyntaxError" in run.errors


@pytest.mark.anyio
async def test_fr08_model_call_limit_is_enforced(memory_db):
    # FR08: the declared model-call ceiling stops the correction loop with a clear reason.
    provider = MockModelProvider(always_fail=True)
    orch = WorkflowOrchestrator(database=memory_db, default_provider=provider, max_retries=1)

    req = CreateRunRequest(code="def task(x): return x", max_model_calls=1)
    run = await orch.execute_run(req)

    assert run.status == RunStatus.FAILED
    assert "model call limit" in (run.errors or "").lower()
    assert run.metrics["model_calls"] == 1


@pytest.mark.anyio
async def test_sandbox_test_verification_integration(memory_db):
    # Provider produces valid refactored code that is verified against a test case
    provider = MockModelProvider()
    orch = WorkflowOrchestrator(database=memory_db, default_provider=provider)

    code = "def compute():\n    return 42\n"
    test_code = "from solution import compute\ndef test_compute():\n    assert compute() == 42\n"
    req = CreateRunRequest(code=code, test_code=test_code)

    run = await orch.execute_run(req)
    assert run.status == RunStatus.COMPLETED
    assert run.verification.tests_available is True
    assert run.verification.tests_passed is True
