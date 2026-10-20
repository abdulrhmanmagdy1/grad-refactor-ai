"""Evaluation harness: arms, test-split guard, case-level records, failures, resume."""

import json
from pathlib import Path

import pytest

from refactor_ai.contracts import (
    ChatMessage,
    Disposition,
    GenerationRequest,
    ModelReviewResult,
    ProviderError,
    ProviderErrorCode,
    ProviderMode,
    ReferenceTestsResult,
    Role,
    RubricCheck,
    RunError,
    RunStatus,
    SyntaxCheck,
    VerificationResult,
    WorkflowMode,
    WorkflowOutcome,
)
from refactor_ai.evaluation import harness, protocol
from refactor_ai.evaluation.records import EvaluationRecord
from refactor_ai.providers import FakeProvider
from refactor_ai.tasks import guard_clauses

ORIGINAL = (
    "def f(x):\n    if x > 0:\n        if x > 9:\n            return 9\n        else:\n"
    "            return x\n    else:\n        raise ValueError('neg')\n"
)
TARGET = guard_clauses.to_guard_clauses(ORIGINAL)
assert guard_clauses.rubric(ORIGINAL, TARGET).passed
RECORD = {
    "id": "gc1-case-01",
    "split": "validation",
    "source": "team-template",
    "source_group": "tpl-case",
    "refactoring_type": "guard_clauses",
    "function_name": "f",
    "original_code": ORIGINAL,
    "target_code": TARGET,
    "license": "LicenseRef-team-authored-pending",
    "provenance": "test fixture",
    "tests": [
        {
            "args": "[1]",
            "kwargs": "{}",
            "expect": {"kind": "return", "value": "1", "exception": None},
        },
        {
            "args": "[0]",
            "kwargs": "{}",
            "expect": {"kind": "raise", "value": None, "exception": "ValueError"},
        },
    ],
}
CONTEXT = harness.EvaluationContext(
    evaluation_id="eval-test",
    protocol_version=protocol.PROTOCOL_VERSION,
    protocol_status="draft",
    dataset_sha256="d" * 64,
    split="validation",
    split_sha256="s" * 64,
    code_sha=None,
)


def verification(disposition, syntax="pass", rubric="pass", tests="pass", review="not_run"):
    return VerificationResult(
        syntax=SyntaxCheck(status=syntax),
        rubric=RubricCheck(status=rubric),
        reference_tests=ReferenceTestsResult(
            status=tests, total=2, passed=2 if tests == "pass" else 1
        ),
        model_review=ModelReviewResult(status=review),
        disposition=disposition,
    )


def stub(outcome_factory, calls=1, role=Role.REFACTOR, use_adapter=None):
    """A workflow stub that makes `calls` provider calls, then returns an outcome."""

    def workflow(request, *, provider, settings, runner):
        assert request.reference_case.case_id == RECORD["id"]
        adapter = settings.refactor_use_adapter if use_adapter is None else use_adapter
        for _ in range(calls):
            provider.generate(
                GenerationRequest(
                    role=role,
                    messages=[ChatMessage(role="user", content=request.code)],
                    use_adapter=adapter if role is Role.REFACTOR else False,
                )
            )
        return outcome_factory(provider)

    return workflow


def completed(provider):
    return WorkflowOutcome(
        status=RunStatus.COMPLETED,
        provider_mode=provider.mode,
        proposed_code=TARGET,
        explanation="e",
        verification=verification(Disposition.PROPOSAL_READY),
        attempt_count=1,
        call_count=1,
        stop_reason="single_role_complete",
    )


def timed_out(provider):
    return WorkflowOutcome(
        status=RunStatus.FAILED,
        provider_mode=provider.mode,
        verification=verification(
            Disposition.FAILED, syntax="not_run", rubric="not_run", tests="not_run"
        ),
        error=RunError(code="timeout", message="slow", stage="generation"),
        stop_reason="provider_error",
    )


def test_arms_follow_the_contract_and_share_generation_settings():
    expected = {
        "A": (WorkflowMode.SINGLE_ROLE, False, 1, 0),
        "B": (WorkflowMode.MULTI_ROLE, False, 5, 1),
        "C": (WorkflowMode.SINGLE_ROLE, True, 1, 0),
        "D": (WorkflowMode.MULTI_ROLE, True, 5, 1),
    }
    generation = None
    for arm, (mode, adapter, calls, corrections) in expected.items():
        settings = protocol.arm_settings(arm)
        assert (settings.mode, settings.refactor_use_adapter) == (mode, adapter)
        assert (settings.max_calls, settings.max_corrections) == (calls, corrections)
        generation = generation or settings.generation
        assert settings.generation == generation
    assert all(config.temperature == 0.0 for config in generation.values())
    assert protocol.parse_arms("a, C,a") == ["A", "C"]
    with pytest.raises(ValueError):
        protocol.parse_arms("A,E")


def write_dataset(path: Path) -> None:
    rows = [
        dict(RECORD, split=split, id=f"gc1-{split}") for split in ("train", "validation", "test")
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_test_split_guard(tmp_path):
    dataset = tmp_path / "records.jsonl"
    write_dataset(dataset)
    kwargs = {"records_path": dataset, "root": tmp_path, "provider_mode": "local_model"}
    assert (
        protocol.authorize_split(
            "validation", confirm_frozen_test=False, protocol_version=None, **kwargs
        )
        is None
    )
    with pytest.raises(protocol.TestSplitRefused, match="i-confirm-frozen-test"):
        protocol.authorize_split(
            "test", confirm_frozen_test=False, protocol_version="eval-v1", **kwargs
        )
    with pytest.raises(protocol.TestSplitRefused, match="protocol-version"):
        protocol.authorize_split("test", confirm_frozen_test=True, protocol_version=None, **kwargs)
    with pytest.raises(protocol.TestSplitRefused, match="not the implemented"):
        protocol.authorize_split(
            "test", confirm_frozen_test=True, protocol_version="eval-v0", **kwargs
        )
    with pytest.raises(protocol.TestSplitRefused, match="not frozen"):
        protocol.authorize_split(
            "test", confirm_frozen_test=True, protocol_version="eval-v1", **kwargs
        )
    freeze = tmp_path / protocol.PROTOCOL_FREEZE_PATH
    freeze.parent.mkdir(parents=True)
    freeze.write_text(
        json.dumps({"status": "frozen", "protocol_version": "eval-v1"}), encoding="utf-8"
    )
    with pytest.raises(protocol.TestSplitRefused, match="local model"):
        protocol.authorize_split(
            "test",
            confirm_frozen_test=True,
            protocol_version="eval-v1",
            records_path=dataset,
            root=tmp_path,
            provider_mode="fake",
        )
    with pytest.raises(protocol.TestSplitRefused, match="No test-split freeze"):
        protocol.authorize_split(
            "test", confirm_frozen_test=True, protocol_version="eval-v1", **kwargs
        )
    test_freeze = tmp_path / protocol.TEST_FREEZE_PATH
    test_freeze.parent.mkdir(parents=True)
    test_freeze.write_text(json.dumps({"split_sha256": "0" * 64}), encoding="utf-8")
    with pytest.raises(protocol.TestSplitRefused, match="differs from the frozen"):
        protocol.authorize_split(
            "test", confirm_frozen_test=True, protocol_version="eval-v1", **kwargs
        )
    actual = protocol.split_sha256(dataset, "test")
    test_freeze.write_text(json.dumps({"split_sha256": actual}), encoding="utf-8")
    evidence = protocol.authorize_split(
        "test", confirm_frozen_test=True, protocol_version="eval-v1", **kwargs
    )
    assert evidence["test_freeze"]["split_sha256"] == actual


def evaluate(workflow, arm="A", provider=None):
    metered = harness.MeteredProvider(provider or FakeProvider())
    return harness.evaluate_case(
        RECORD, arm, workflow=workflow, provider=metered, runner=None, context=CONTEXT
    )


def test_completed_record_has_every_measurement():
    record = evaluate(stub(completed))
    assert isinstance(record, EvaluationRecord)
    assert record.run_status == "completed" and record.failure_type == "none"
    assert record.proposal_ready and record.disposition == "proposal_ready"
    assert record.recheck.syntax == "pass" and record.recheck.rubric == "pass"
    assert record.recheck.agrees_with_workflow is True
    assert record.call_count == 1 and record.calls_by_role == {"refactor": 1}
    assert record.prompt_tokens is not None and record.completion_tokens is not None
    assert record.worker_peak_rss_mb is None and "worker_peak_rss_mb" in record.null_reasons
    assert record.gpu_memory_used_mb is None and "gpu_memory_used_mb" in record.null_reasons
    assert "model_evidence" in record.null_reasons  # fake provider output is labelled
    assert record.input_sha256 and record.output_sha256 and record.warnings == []
    assert EvaluationRecord.model_validate_json(record.model_dump_json()) == record


def test_failures_are_recorded_with_types():
    timeout = evaluate(stub(timed_out))
    assert timeout.run_status == "failed" and timeout.failure_type == "provider_timeout"
    assert not timeout.proposal_ready and timeout.disposition == "failed"
    assert timeout.recheck.syntax == "no_output" and timeout.proposed_code is None
    assert "proposed_code" in timeout.null_reasons

    def raises(request, **_kwargs):
        raise RuntimeError("boom")

    crashed = evaluate(raises)
    assert crashed.failure_type == "harness_exception" and crashed.run_status is None
    assert crashed.reference_tests.status == "not_run" and crashed.disposition == "failed"
    assert crashed.error["code"] == "harness_exception"

    wrong_type = evaluate(lambda request, **_kwargs: {"status": "completed"})
    assert wrong_type.failure_type == "harness_exception"


def test_tokens_are_null_with_reason_when_the_provider_does_not_report_them():
    class Silent(FakeProvider):
        def generate(self, request):
            return super().generate(request).model_copy(update={"prompt_tokens": None})

    record = evaluate(stub(completed), provider=Silent())
    assert record.prompt_tokens is None and record.completion_tokens is not None
    assert "for 1 of 1 calls" in record.null_reasons["prompt_tokens"]


def test_budget_and_adapter_violations_become_warnings():
    over = evaluate(stub(completed, calls=2), arm="A")
    assert any(w.startswith("budget_violation") for w in over.warnings)
    wrong_adapter = evaluate(stub(completed, use_adapter=False), arm="C")
    assert any(w.startswith("adapter_flag_mismatch") for w in wrong_adapter.warnings)
    fine = evaluate(stub(completed), arm="C")
    assert not any(w.startswith(("budget", "adapter")) for w in fine.warnings)


def test_recheck_detects_disagreement_with_the_workflow():
    def lying(provider):
        outcome = completed(provider)
        return outcome.model_copy(update={"proposed_code": ORIGINAL})  # claims rubric pass

    record = evaluate(stub(lying))
    assert record.rubric == "pass" and record.recheck.rubric == "fail"
    assert record.recheck.agrees_with_workflow is False


def test_run_evaluation_writes_every_attempt_and_resumes(tmp_path):
    records = [dict(RECORD, id=f"gc1-case-{i:02d}") for i in range(3)]

    def workflow(request, *, provider, settings, runner):
        return completed(provider)

    output = tmp_path / "run" / "records.jsonl"
    summary = harness.run_evaluation(
        records,
        ["A", "B"],
        workflow=workflow,
        provider=FakeProvider(),
        runner=None,
        context=CONTEXT,
        output_path=output,
    )
    assert summary["written_by_arm"] == {"A": 3, "B": 3}
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [(r["case_id"][-2:], r["arm"], r["order_position"]) for r in rows] == [
        ("00", "A", 0),
        ("00", "B", 1),
        ("01", "B", 0),
        ("01", "A", 1),
        ("02", "A", 0),
        ("02", "B", 1),
    ]
    with pytest.raises(FileExistsError):
        harness.run_evaluation(
            records,
            ["A"],
            workflow=workflow,
            provider=FakeProvider(),
            runner=None,
            context=CONTEXT,
            output_path=output,
        )
    resumed = harness.run_evaluation(
        records,
        ["A", "B", "C"],
        workflow=workflow,
        provider=FakeProvider(),
        runner=None,
        context=CONTEXT,
        output_path=output,
        resume=True,
    )
    assert resumed["written_by_arm"] == {"C": 3} and resumed["skipped_existing"] == 6
    assert len(output.read_text(encoding="utf-8").splitlines()) == 9


def test_metered_provider_forwards_and_counts():
    inner = FakeProvider(
        script={Role.REFACTOR: [ProviderError(code=ProviderErrorCode.TIMEOUT, message="t")]}
    )
    metered = harness.MeteredProvider(inner)
    assert metered.mode is ProviderMode.FAKE and metered.info().provider_mode is ProviderMode.FAKE
    result = metered.generate(
        GenerationRequest(role=Role.REFACTOR, messages=[ChatMessage(role="user", content="x")])
    )
    assert result.error.code is ProviderErrorCode.TIMEOUT
    assert len(metered.take_calls()) == 1 and metered.take_calls() == []


def test_warm_up_runs_once_per_adapter_state():
    provider = FakeProvider()
    report = harness.warm_up(provider, None, ["A", "C", "D"])
    assert [call["use_adapter"] for call in report["provider_calls"]] == [False, True]
    assert len(provider.calls) == 2
