"""Unit tests for model providers (Mock and Local)."""

import pytest

from core.ast_analyzer import analyze
from core.exceptions import ExecutionTimeoutError
from core.schemas import ASTFinding
from models.local_provider import LocalModelProvider
from models.mock_provider import MockModelProvider


@pytest.mark.anyio
async def test_mock_provider_refactors_long_function():
    provider = MockModelProvider()
    code = "def big_task():\n" + "    x = 1\n" * 35 + "    return x\n"
    analysis = analyze(code)
    assert len(analysis.findings) > 0

    refactored, meta = await provider.generate_refactoring(code, analysis.findings)
    assert "_big_task_chunk" in refactored
    assert "def big_task" in refactored
    assert meta["provider"] == "mock"
    assert meta["total_tokens"] > 0

    # Ensure refactored code has valid syntax
    refact_analysis = analyze(refactored)
    assert refact_analysis.syntax_valid is True


@pytest.mark.anyio
async def test_mock_provider_retry_loop_simulation():
    # Test provider that fails on first try but succeeds on retry
    provider = MockModelProvider(fail_on_first_try=True)
    findings = [
        ASTFinding(
            rule="deep-nesting",
            line=5,
            node_type="If",
            message="deep nesting",
            rationale="guard clauses",
        )
    ]
    code = (
        "def process(x):\n"
        "    if x:\n"
        "        if x > 1:\n"
        "            if x > 2:\n"
        "                return x\n"
    )

    # First attempt: invalid code
    bad_code, meta1 = await provider.generate_refactoring(code, findings, options={})
    assert "syntax_error_simulation" in bad_code
    assert meta1["is_retry"] is False

    # Second attempt with retry_feedback: valid code
    good_code, meta2 = await provider.generate_refactoring(
        code, findings, options={"retry_feedback": "SyntaxError at line 1"}
    )
    assert "syntax_error_simulation" not in good_code
    assert meta2["is_retry"] is True
    assert analyze(good_code).syntax_valid is True


@pytest.mark.anyio
async def test_mock_provider_timeout():
    provider = MockModelProvider(simulate_timeout=True)
    with pytest.raises(ExecutionTimeoutError):
        await provider.generate_refactoring("def f(): pass", [])


@pytest.mark.anyio
async def test_mock_provider_explain_changes():
    provider = MockModelProvider()
    explanation = await provider.explain_changes(
        original_code="def long_fn():\n" + "    pass\n" * 40,
        refactored_code="def _long_fn_chunk(): pass\ndef long_fn(): pass",
        diff="--- a\n+++ b",
    )
    assert "helper" in explanation.lower() or "extracted" in explanation.lower()


@pytest.mark.anyio
async def test_local_provider_cpu_fallback():
    # Local provider falls back cleanly without torch/transformers on CPU
    provider = LocalModelProvider(model_name="test-model")
    code = "def small(): return 42"
    refactored, meta = await provider.generate_refactoring(code, [])
    assert meta["provider"] in ("local-cpu-fallback", "local-hf")
    assert analyze(refactored).syntax_valid is True
