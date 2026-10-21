"""Evaluation harness: arms, test-split guard, case-level records, failures, resume."""

import hashlib
import importlib.util
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
    RunnerInfo,
    RunStatus,
    SyntaxCheck,
    VerificationResult,
    WorkflowMode,
    WorkflowOutcome,
)
from refactor_ai.evaluation import cases, harness, protocol, report
from refactor_ai.evaluation.records import EvaluationRecord, RecordFileError
from refactor_ai.providers import FakeProvider
from refactor_ai.providers.base import failed_result
from refactor_ai.tasks import guard_clauses

EVALUATE_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "evaluate.py"

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
    case_fields = {
        "source_url": None,
        "task_version": 1,
        "prompt": "Task: guard_clauses\nCode:\n```python\n" + ORIGINAL + "```",
        "completion": "```python\n" + TARGET + "```\nExplanation: guard clauses",
    }
    rows = [
        dict(RECORD, split=split, id=f"gc1-{split}", **case_fields)
        for split in ("train", "validation", "test")
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def frozen_record(dataset: Path) -> dict:
    """A protocol freeze record that matches the dataset, the harness and this code."""
    from refactor_ai.data import content

    rows = content.records_from_text(dataset.read_text(encoding="utf-8"))
    return {
        "protocol_version": "eval-v1",
        "status": "frozen",
        "model": dict(FROZEN_MODEL),
        "arms": protocol.frozen_arm_settings(),
        "data": {
            "dataset_sha256": cases.dataset_sha256(dataset),
            "test_split": {
                "split_sha256": protocol.split_sha256(dataset, "test"),
                "content_sha256": content.content_sha256(rows, "test"),
                "count": sum(row["split"] == "test" for row in rows),
            },
        },
        "frozen_code": {"files": protocol.frozen_code_sha256()},
    }


def write_freezes(root: Path, freeze: dict, test_freeze: dict | None = None) -> None:
    path = root / protocol.PROTOCOL_FREEZE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(freeze), encoding="utf-8")
    test_path = root / protocol.TEST_FREEZE_PATH
    if test_freeze is None:
        test_path.unlink(missing_ok=True)
    else:
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text(json.dumps(test_freeze), encoding="utf-8")


def test_test_split_guard(tmp_path):
    dataset = tmp_path / "records.jsonl"
    write_dataset(dataset)
    kwargs = {"records_path": dataset, "root": tmp_path, "provider_mode": "local_model"}
    confirmed = {"confirm_frozen_test": True, "protocol_version": "eval-v1", **kwargs}
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
        protocol.authorize_split("test", **confirmed)
    good = frozen_record(dataset)
    write_freezes(tmp_path, dict(good, status="draft"))
    with pytest.raises(protocol.TestSplitRefused, match="not frozen"):
        protocol.authorize_split("test", **confirmed)
    write_freezes(tmp_path, good)
    with pytest.raises(protocol.TestSplitRefused, match="local model"):
        protocol.authorize_split("test", **dict(confirmed, provider_mode="fake"))

    # Exactly this record is accepted, with or without the test-split freeze record.
    evidence = protocol.authorize_split("test", **confirmed)
    assert evidence == {"test_freeze": None, "protocol_freeze": good}
    split = good["data"]["test_split"]
    test_freeze = {"split_sha256": split["split_sha256"], "content_sha256": split["content_sha256"]}
    write_freezes(tmp_path, good, test_freeze)
    assert protocol.authorize_split("test", **confirmed)["test_freeze"] == test_freeze


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda f: f.update(protocol_version="eval-v2"), "is not frozen"),
        (lambda f: f["data"]["test_split"].update(split_sha256="0" * 64), "split_sha256"),
        (lambda f: f["data"]["test_split"].update(content_sha256="0" * 64), "content_sha256"),
        (lambda f: f["data"]["test_split"].update(count=87), "count 1 differs"),
        (lambda f: f["data"].update(dataset_sha256="0" * 64), "dataset hash"),
        (lambda f: f["arms"]["D"].update(max_corrections=0), "arm D"),
        (
            lambda f: f["arms"]["A"]["generation"]["review"].update(max_new_tokens=768),
            "arm A",
        ),
        (lambda f: f["arms"].pop("C"), "exactly the arms"),
        (lambda f: f["model"].pop("adapter_sha256"), "model.adapter_sha256 is missing"),
        (lambda f: f["model"].update(adapter_sha256="abc"), "not a SHA-256"),
        (lambda f: f.pop("model"), "no 'model' object"),
        (
            lambda f: f["frozen_code"]["files"].update({"scripts/evaluate.py": "0" * 64}),
            "frozen code changed since the freeze: scripts/evaluate.py",
        ),
        (
            lambda f: f["frozen_code"]["files"].update({"src/refactor_ai/gone.py": "0" * 64}),
            "frozen code missing since the freeze: src/refactor_ai/gone.py",
        ),
        (
            lambda f: f["frozen_code"]["files"].pop("src/refactor_ai/task_format.py"),
            "frozen code new since the freeze: src/refactor_ai/task_format.py",
        ),
        (lambda f: f.pop("frozen_code"), "lists no frozen code"),
    ],
)
def test_test_split_guard_refuses_any_other_freeze_record(tmp_path, change, expected):
    dataset = tmp_path / "records.jsonl"
    write_dataset(dataset)
    freeze = frozen_record(dataset)
    change(freeze)
    write_freezes(tmp_path, freeze)
    with pytest.raises(protocol.TestSplitRefused) as refused:
        protocol.authorize_split(
            "test",
            confirm_frozen_test=True,
            protocol_version="eval-v1",
            records_path=dataset,
            root=tmp_path,
            provider_mode="local_model",
        )
    assert expected in str(refused.value)


def test_test_split_guard_needs_both_freeze_records_to_agree(tmp_path):
    dataset = tmp_path / "records.jsonl"
    write_dataset(dataset)
    freeze = frozen_record(dataset)
    split = freeze["data"]["test_split"]
    write_freezes(
        tmp_path, freeze, {"split_sha256": "0" * 64, "content_sha256": split["content_sha256"]}
    )
    kwargs = {"records_path": dataset, "root": tmp_path, "provider_mode": "local_model"}
    with pytest.raises(protocol.TestSplitRefused, match="test-split-freeze.json has split_sha256"):
        protocol.authorize_split(
            "test", confirm_frozen_test=True, protocol_version="eval-v1", **kwargs
        )
    # A changed test case no longer matches the frozen split and content hashes.
    rows = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines()]
    rows[-1]["tests"] = rows[-1]["tests"][:1]
    dataset.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    write_freezes(tmp_path, freeze)
    with pytest.raises(protocol.TestSplitRefused, match="content_sha256"):
        protocol.authorize_split(
            "test", confirm_frozen_test=True, protocol_version="eval-v1", **kwargs
        )


def test_frozen_code_hashes_read_crlf_as_lf(tmp_path):
    for pattern in protocol.FROZEN_CODE_PATTERNS:
        name = pattern.replace("*", "module")
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(b"x = 1\r\ny = 2\r\n")
    (tmp_path / "src/refactor_ai/providers/fake.py").write_text("ignored\n", encoding="utf-8")
    hashes = protocol.frozen_code_sha256(tmp_path)
    assert len(hashes) == len(protocol.FROZEN_CODE_PATTERNS)
    assert "src/refactor_ai/providers/fake.py" not in hashes
    expected = hashlib.sha256(b"x = 1\ny = 2\n").hexdigest()
    assert set(hashes.values()) == {expected}


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


class StubRunner:
    """Stands in for the trusted runner: every reference test passes (2 of 2)."""

    def __init__(self, enabled=True, reason=None):
        self._info = RunnerInfo(enabled=enabled, reason=reason)

    def info(self):
        return self._info

    def run(self, case, candidate_code, *, timeout_s=None):
        return ReferenceTestsResult(
            status="pass", case_id=case.case_id, total=2, passed=2, failed=0, errored=0
        )


def test_a_run_that_fails_in_review_reports_no_checked_proposal():
    from refactor_ai.agents.coordinator import run_workflow

    timeout = ProviderError(code=ProviderErrorCode.TIMEOUT, message="slow")
    provider = harness.MeteredProvider(FakeProvider(script={Role.REVIEW: [timeout]}))
    record = harness.evaluate_case(
        RECORD, "B", workflow=run_workflow, provider=provider, runner=StubRunner(), context=CONTEXT
    )
    assert record.run_status == "failed" and record.failure_type == "provider_timeout"
    assert record.error["stage"] == "review" and record.proposed_code is None
    # The workflow checked its last proposal before the review timed out, but the run has
    # no final proposal, so none of these outcomes may count as a success.
    assert (record.syntax, record.rubric, record.reference_tests.status) == ("not_run",) * 3
    assert record.rubric_failed_checks == [] and not record.proposal_ready
    kept = [w for w in record.warnings if w.startswith("failed_run_checks:")]
    assert len(kept) == 1 and "reference_tests=pass" in kept[0]
    rates = report.arm_metrics([json.loads(record.model_dump_json())])["B"]["rates"]
    for name in ("syntax_valid", "rubric_pass", "tests_pass", "tests_executed"):
        assert rates[name]["numerator"] == 0, name
    assert rates["failed"]["numerator"] == 1 and rates["timeouts"]["numerator"] == 1


LINE_SEPARATORS = "\u2028\u2029\u0085"


def test_unicode_line_separators_in_model_output_keep_records_readable(tmp_path):
    answer = "```python\n" + TARGET + "```\nExplanation: guard\u2028clauses\u2029done\u0085."

    def with_separators(provider):
        return completed(provider).model_copy(update={"explanation": "a\u2028b\u2029c\u0085d"})

    output = tmp_path / "records.jsonl"
    harness.run_evaluation(
        [RECORD],
        ["A"],
        workflow=stub(with_separators),
        provider=FakeProvider(script={Role.REFACTOR: [answer]}),
        runner=None,
        context=CONTEXT,
        output_path=output,
    )
    raw = output.read_bytes()
    assert raw.count(b"\n") == 1  # one physical line per record
    assert not any(ch.encode("utf-8") in raw for ch in LINE_SEPARATORS)  # escaped by the writer
    row = json.loads(raw)
    assert row["calls"][0]["output"] == answer and row["explanation"] == "a\u2028b\u2029c\u0085d"
    assert harness.existing_attempts(output) == {(RECORD["id"], "A")}

    # A file from a JSON writer that leaves the characters raw is still one record per line.
    other = tmp_path / "raw.jsonl"
    other.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    assert all(ch.encode("utf-8") in other.read_bytes() for ch in LINE_SEPARATORS)
    assert harness.existing_attempts(other) == {(RECORD["id"], "A")}
    assert cases.load_records(other) == [row]
    resumed = harness.run_evaluation(
        [RECORD],
        ["A", "B"],
        workflow=stub(completed),
        provider=FakeProvider(),
        runner=None,
        context=CONTEXT,
        output_path=other,
        resume=True,
    )
    assert resumed["written_by_arm"] == {"B": 1} and resumed["skipped_existing"] == 1


def test_resume_moves_an_interrupted_last_line_aside(tmp_path):
    records = [dict(RECORD, id=f"gc1-case-{i:02d}") for i in range(2)]
    output = tmp_path / "run" / "records.jsonl"

    def workflow(request, *, provider, settings, runner):
        return completed(provider)

    def run(arms, resume):
        return harness.run_evaluation(
            records,
            arms,
            workflow=workflow,
            provider=FakeProvider(),
            runner=None,
            context=CONTEXT,
            output_path=output,
            resume=resume,
        )

    run(["A"], resume=False)
    data = output.read_bytes()
    first_end = data.index(b"\n") + 1
    partial = data[first_end : first_end + (len(data) - first_end) // 2]
    output.write_bytes(data[:first_end] + partial)  # an interrupted write of record 2

    with pytest.raises(RecordFileError, match=rf"line 2 \(byte offset {first_end}\)"):
        harness.existing_attempts(output)
    summary = run(["A"], resume=True)
    assert summary["written_by_arm"] == {"A": 1} and summary["skipped_existing"] == 1
    repaired = summary["repaired_last_line"]
    assert repaired["offset"] == first_end and repaired["bytes"] == len(partial)
    assert Path(repaired["moved_to"]).read_bytes() == partial  # kept, not deleted
    rows = report.load_records([output])
    assert [row["case_id"] for row in rows] == ["gc1-case-00", "gc1-case-01"]

    # A complete last record that only lost its newline is kept and terminated.
    output.write_bytes(output.read_bytes()[:-1])
    summary = run(["A", "B"], resume=True)
    assert summary["skipped_existing"] == 2 and summary["written_by_arm"] == {"B": 2}
    assert summary["repaired_last_line"]["moved_to"] is None
    assert len(report.load_records([output])) == 4


class WorkerProvider(FakeProvider):
    """A provider with a model worker: a timeout stops it, and the next call reloads it."""

    def __init__(self, stop_on: str):
        super().__init__()
        self.alive = False
        self.stop_on = stop_on
        self.loads: list[str] = []  # the user message of each call that paid a model load

    @property
    def worker_pid(self):
        return 4242 if self.alive else None

    def generate(self, request):
        content = request.messages[-1].content
        if not self.alive:
            self.alive = True
            self.loads.append(content)
        if self.stop_on in content:
            self.alive = False
            return failed_result(self.mode, ProviderErrorCode.TIMEOUT, "slow", 0.0)
        return super().generate(request)


def test_a_stopped_model_worker_is_warmed_up_again_before_the_next_attempt(tmp_path):
    records = [dict(RECORD, id=f"gc1-case-{i:02d}") for i in range(3)]

    def workflow(request, *, provider, settings, runner):
        message = ChatMessage(role="user", content=request.reference_case.case_id)
        result = provider.generate(
            GenerationRequest(
                role=Role.REFACTOR, messages=[message], use_adapter=settings.refactor_use_adapter
            )
        )
        return timed_out(provider) if result.error else completed(provider)

    provider = WorkerProvider(stop_on="gc1-case-00")
    harness.warm_up(provider, None, ["A"])  # evaluate.py warms up before the first attempt
    summary = harness.run_evaluation(
        records,
        ["A"],
        workflow=workflow,
        provider=provider,
        runner=None,
        context=CONTEXT,
        output_path=tmp_path / "records.jsonl",
    )
    rows = report.load_records([tmp_path / "records.jsonl"])
    assert [row["failure_type"] for row in rows] == ["provider_timeout", "none", "none"]
    # Both model loads were paid by untimed warm-up calls, none by a timed attempt.
    assert len(provider.loads) == 2 and all("def warm_up(" in m for m in provider.loads)
    assert [(item["after_case"], item["after_arm"]) for item in summary["rewarm"]] == [
        ("gc1-case-00", "A")
    ]
    assert summary["rewarm"][0]["provider_calls"][0]["error"] is None
    assert [row["call_count"] for row in rows] == [1, 1, 1]


# --- scripts/evaluate.py -------------------------------------------------------------


@pytest.fixture
def evaluate_script(monkeypatch):
    spec = importlib.util.spec_from_file_location("evaluate_script", EVALUATE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "git_head", lambda: None)
    return module


def cli(dataset: Path, out: Path, *extra: str) -> list[str]:
    return ["--dataset", str(dataset), "--output-dir", str(out), *extra]


def test_resume_needs_the_evaluation_id_of_an_existing_run(
    tmp_path, monkeypatch, evaluate_script, capsys
):
    dataset = tmp_path / "records.jsonl"
    write_dataset(dataset)
    out = tmp_path / "out"

    def no_provider(*_args):
        raise AssertionError("no provider may be built for a refused run")

    monkeypatch.setattr(evaluate_script, "make_provider", no_provider)
    base = cli(dataset, out, "--split", "validation", "--provider", "fake", "--runner", "disabled")
    assert evaluate_script.main([*base, "--resume"]) == 2
    assert "--evaluation-id" in capsys.readouterr().err
    assert evaluate_script.main([*base, "--resume", "--evaluation-id", "lost"]) == 2
    assert "nothing to resume" in capsys.readouterr().err
    assert not out.exists()


def test_each_run_segment_keeps_its_own_manifest(tmp_path, evaluate_script, capsys):
    dataset = tmp_path / "records.jsonl"
    write_dataset(dataset)
    out = tmp_path / "out"
    base = cli(dataset, out, "--split", "validation", "--provider", "fake", "--runner", "disabled")
    base += ["--evaluation-id", "seg"]
    assert evaluate_script.main([*base, "--arms", "A"]) == 0
    printed = capsys.readouterr().out
    assert f"Evaluation seg: records go to {out / 'seg' / 'records.jsonl'}" in printed
    first = json.loads((out / "seg" / "run.json").read_text(encoding="utf-8"))
    assert evaluate_script.main([*base, "--arms", "B", "--resume"]) == 0
    assert json.loads((out / "seg" / "run.json").read_text(encoding="utf-8")) == first
    later = sorted((out / "seg").glob("run-*.json"))
    assert len(later) == 1
    second = json.loads(later[0].read_text(encoding="utf-8"))
    assert list(first["arms"]) == ["A"] and list(second["arms"]) == ["B"]
    assert first["summary"]["written_by_arm"] == {"A": 1} and first["finished_at"]
    assert second["summary"]["skipped_existing"] == 1 and second["resumed"] is True
    assert second["earlier_manifests"] == ["run.json"]
    assert len(report.load_records([out / "seg" / "records.jsonl"])) == 2


FROZEN_MODEL = {
    "model_id": "fake-provider",
    "model_revision": "fake-v1",
    "adapter_id": "lora-guard-clauses",
    "adapter_sha256": "a" * 64,
}


class ClosingProvider(FakeProvider):
    """FakeProvider that remembers being closed, reports a given identity, can lack an adapter."""

    def __init__(self, adapter_available=True, model=None):
        super().__init__()
        self.closed = False
        self.adapter_available = adapter_available
        self.model = model

    def close(self):
        self.closed = True

    def generate(self, request):
        if request.use_adapter and not self.adapter_available:
            message = "use_adapter=true but no LoRA adapter is configured"
            return failed_result(self.mode, ProviderErrorCode.UNAVAILABLE, message)
        result = super().generate(request)
        if self.model is not None:
            identity = dict(self.model, use_adapter=request.use_adapter)
            result = result.model_copy(update={"model": result.model.model_copy(update=identity)})
        return result


def test_a_test_split_run_stops_before_any_attempt_unless_it_is_complete_and_ready(
    tmp_path, monkeypatch, evaluate_script, capsys
):
    dataset = tmp_path / "records.jsonl"
    write_dataset(dataset)
    write_freezes(tmp_path, frozen_record(dataset))
    monkeypatch.setattr(evaluate_script, "ROOT", tmp_path)
    out = tmp_path / "out"
    built: list[ClosingProvider] = []
    setup = {"provider": ClosingProvider, "runner": StubRunner}

    def make_provider(kind, config):
        built.append(setup["provider"]())
        return built[-1]

    monkeypatch.setattr(evaluate_script, "make_provider", make_provider)
    monkeypatch.setattr(evaluate_script, "make_runner", lambda mode: setup["runner"]())
    base = cli(dataset, out, "--split", "test", "--provider", "local", "--i-confirm-frozen-test")
    base += ["--protocol-version", "eval-v1"]

    # A partial test run or one without the runner is refused before any model loads.
    for extra in (["--limit", "1"], ["--case-ids", "gc1-test"], ["--runner", "disabled"]):
        assert evaluate_script.main([*base, *extra]) == 2
        assert "Refused" in capsys.readouterr().err
    assert built == []

    def refused(arms: str, expected: str) -> None:
        assert evaluate_script.main([*base, "--arms", arms]) == 2
        error = capsys.readouterr().err
        assert "before its first attempt" in error and expected in error, error
        assert built[-1].closed

    setup["runner"] = lambda: StubRunner(enabled=False, reason="isolation self-checks failed")
    setup["provider"] = lambda: ClosingProvider(model=FROZEN_MODEL)
    refused("A", "isolation self-checks failed")
    setup["runner"] = StubRunner
    setup["provider"] = lambda: ClosingProvider(adapter_available=False, model=FROZEN_MODEL)
    refused("A,C", "use_adapter=true")
    setup["provider"] = lambda: ClosingProvider(model=dict(FROZEN_MODEL, adapter_sha256="b" * 64))
    refused("C", "adapter_sha256")
    setup["provider"] = lambda: ClosingProvider(model=dict(FROZEN_MODEL, model_revision="other"))
    refused("A", "model_revision")
    assert not list(out.rglob("records.jsonl"))

    # With the runner enabled and the frozen model identity, the run goes ahead.
    setup["provider"] = lambda: ClosingProvider(model=FROZEN_MODEL)
    assert evaluate_script.main([*base, "--arms", "A,C", "--evaluation-id", "final"]) == 0
    rows = report.load_records([out / "final" / "records.jsonl"])
    assert sorted((row["case_id"], row["arm"]) for row in rows) == [
        ("gc1-test", "A"),
        ("gc1-test", "C"),
    ]
    assert all(row["reference_tests"]["status"] == "pass" for row in rows)


def test_test_readiness_needs_the_frozen_model_identity():
    call = {"use_adapter": True, "error": None, "model": dict(FROZEN_MODEL, use_adapter=False)}
    warmup = {"runner": {"enabled": True, "reason": None}, "provider_calls": [call]}
    with pytest.raises(protocol.TestSplitRefused, match="reported use_adapter=false"):
        protocol.check_test_readiness(warmup, {"protocol_freeze": {"model": FROZEN_MODEL}})
    with pytest.raises(protocol.TestSplitRefused, match="names no model identity"):
        protocol.check_test_readiness(warmup, {"protocol_freeze": {"status": "frozen"}})
    call["model"]["use_adapter"] = True
    protocol.check_test_readiness(warmup, {"protocol_freeze": {"model": FROZEN_MODEL}})
