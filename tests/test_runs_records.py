"""Record helpers and the error vocabulary."""

import ast
from datetime import UTC, datetime, timedelta

import pytest

from refactor_ai.contracts import (
    Disposition,
    ModelReviewResult,
    ProviderMode,
    ReferenceCase,
    ReferenceTestsResult,
    RubricCheck,
    RunRecord,
    RunStatus,
    SyntaxCheck,
    VerificationResult,
    WorkflowMode,
    WorkflowOutcome,
)
from refactor_ai.runs import errors
from refactor_ai.runs.records import (
    OUTCOME_FIELDS,
    apply_outcome,
    disposition_of,
    is_valid_run_id,
    matches_reference_case,
    new_record,
    new_run_id,
    normalize_newlines,
    proposal_problem,
    summarize,
)

T0 = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
CODE = "def f(x):\n    return x\n"


def record(**update) -> RunRecord:
    base = new_record(
        run_id=new_run_id(),
        created_at=T0,
        code=CODE,
        task_type="guard_clauses",
        workflow_mode=WorkflowMode.MULTI_ROLE,
        provider_mode=ProviderMode.FAKE,
    )
    return base.model_copy(update=update)


def verification(disposition: Disposition) -> VerificationResult:
    return VerificationResult(
        syntax=SyntaxCheck(status="pass"),
        rubric=RubricCheck(status="pass"),
        reference_tests=ReferenceTestsResult(status="not_available"),
        model_review=ModelReviewResult(status="not_run"),
        disposition=disposition,
    )


def test_run_ids_are_unguessable_url_safe_hex():
    ids = {new_run_id() for _ in range(1000)}
    assert len(ids) == 1000
    assert all(is_valid_run_id(run_id) for run_id in ids)
    for bad in ("", "a" * 31, "a" * 33, "A" * 32, "g" * 32, "../" + "a" * 29, "a" * 31 + "\n"):
        assert not is_valid_run_id(bad)


def test_newline_normalization_and_reference_matching():
    assert normalize_newlines("a\r\nb\rc\n") == "a\nb\nc\n"
    reference = ReferenceCase(
        case_id="demo", task_type="guard_clauses", function_name="f", original_code=CODE
    )
    assert matches_reference_case(CODE, reference)
    assert matches_reference_case(CODE.replace("\n", "\r\n"), reference)
    assert matches_reference_case(CODE.rstrip("\n"), reference)
    assert matches_reference_case(CODE + "\n\n  \n", reference)
    assert not matches_reference_case("  " + CODE, reference)
    assert not matches_reference_case(CODE.replace("x", "y"), reference)


def test_outcome_mapping_covers_every_workflow_outcome_field():
    # A new WorkflowOutcome field must be mapped deliberately into the run record.
    assert set(OUTCOME_FIELDS) == set(WorkflowOutcome.model_fields)
    assert set(OUTCOME_FIELDS) <= set(RunRecord.model_fields)


def test_apply_outcome_keeps_identity_and_input():
    original = record(started_at=T0 + timedelta(seconds=1), status=RunStatus.VERIFYING)
    outcome = WorkflowOutcome(
        status=RunStatus.COMPLETED,
        provider_mode=ProviderMode.LOCAL_MODEL,
        proposed_code="def f(x):\n    return x\n",
        verification=verification(Disposition.UNCERTAIN),
        call_count=1,
        warnings=["note"],
    )
    finished = apply_outcome(original, outcome, T0 + timedelta(seconds=2))
    assert finished.run_id == original.run_id
    assert finished.created_at == original.created_at
    assert finished.started_at == original.started_at
    assert finished.original_code == original.original_code
    assert finished.settings == original.settings
    assert finished.status == RunStatus.COMPLETED
    assert finished.provider_mode == ProviderMode.LOCAL_MODEL
    assert finished.finished_at == T0 + timedelta(seconds=2)
    assert (finished.call_count, finished.warnings) == (1, ["note"])


def test_disposition_and_summary():
    assert disposition_of(record()) is None
    assert disposition_of(record(status=RunStatus.FAILED)) == Disposition.FAILED
    done = record(status=RunStatus.COMPLETED, verification=verification(Disposition.REJECTED))
    assert disposition_of(done) == Disposition.REJECTED
    summary = summarize(done.model_copy(update={"human_decision": "rejected"}))
    assert summary.run_id == done.run_id
    assert summary.disposition == Disposition.REJECTED
    assert summary.human_decision == "rejected"


def test_proposal_rules():
    assert proposal_problem(record()) == errors.PROPOSAL_NOT_FINISHED
    assert proposal_problem(record(status=RunStatus.GENERATING, proposed_code=CODE)) == (
        errors.PROPOSAL_NOT_FINISHED
    )
    assert proposal_problem(record(status=RunStatus.COMPLETED)) == errors.PROPOSAL_MISSING
    assert proposal_problem(record(status=RunStatus.COMPLETED, proposed_code="")) == (
        errors.PROPOSAL_MISSING
    )
    assert proposal_problem(record(status=RunStatus.FAILED, proposed_code=CODE)) == (
        errors.PROPOSAL_MISSING
    )
    assert proposal_problem(record(status=RunStatus.COMPLETED, proposed_code=CODE)) is None


# --- error vocabulary ----------------------------------------------------------------


def test_validation_error_summarizes_without_echoing_input():
    error = errors.validation_error(
        [
            {"loc": ("body", "code"), "msg": "Value error, code must not be blank", "type": "v"},
            {"loc": ("body", "workflow_mode"), "msg": "Input should be ...", "type": "enum"},
        ]
    )
    assert error.status_code == 422
    assert error.message == "Invalid request (code): code must not be blank (and 1 more problem(s))"
    assert error.details[1] == {
        "loc": ["body", "workflow_mode"],
        "message": "Input should be ...",
        "type": "enum",
    }
    body_only = errors.validation_error([{"loc": ("body",), "msg": "Field required", "type": "m"}])
    assert body_only.message == "Invalid request (body): Field required"
    bad_json = errors.validation_error(
        [{"loc": ("body", 7), "msg": "JSON decode error", "type": "json_invalid"}]
    )
    assert bad_json.message == "Invalid request (body): JSON decode error"
    assert bad_json.details[0]["loc"] == ["body", 7]
    indexed = errors.validation_error([{"loc": ("query", "limit"), "msg": "too big", "type": "t"}])
    assert indexed.message == "Invalid request (query.limit): too big"
    assert errors.validation_error([]).message == "Invalid request."


def test_invalid_syntax_reports_positions_when_known():
    try:
        ast.parse("def f(:\n    pass\n")
    except SyntaxError as exc:
        located = errors.invalid_syntax(exc)
    assert located.details == [{"line": 1, "column": 7, "message": "invalid syntax"}]
    assert located.message.endswith("(line 1, column 7).")
    no_position = errors.invalid_syntax(SyntaxError("bad"))
    assert no_position.details == [{"line": None, "column": None, "message": "bad"}]
    assert "the code is too deeply nested" in errors.invalid_syntax(RecursionError()).message
    assert "too deeply nested" in errors.invalid_syntax(MemoryError()).message
    assert "UTF-8" in errors.invalid_syntax(UnicodeEncodeError("utf-8", "x", 0, 1, "r")).message
    assert "null bytes" in errors.invalid_syntax(ValueError("null bytes")).message


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (errors.unknown_reference_case("x"), 422, "unknown_reference_case"),
        (errors.reference_case_mismatch("x"), 422, "reference_case_mismatch"),
        (errors.busy(4), 503, "busy"),
        (errors.service_unavailable(), 503, "service_unavailable"),
        (errors.run_not_found(), 404, "run_not_found"),
        (errors.proposal_unavailable(errors.PROPOSAL_MISSING), 409, "proposal_unavailable"),
        (errors.reference_cases_unavailable(), 500, "reference_cases_unavailable"),
        (errors.payload_too_large(), 413, "payload_too_large"),
        (errors.not_found(), 404, "not_found"),
        (errors.method_not_allowed("GET"), 405, "method_not_allowed"),
        (errors.internal_error(), 500, "internal_error"),
        (errors.cors_rejected("origin"), 400, "cors_rejected"),
    ],
)
def test_error_builders(error, status, code):
    assert error.status_code == status
    assert error.code == code
    body = error.body()
    assert body.error.code == code and body.error.message


def test_busy_carries_retry_after():
    assert errors.busy(4).headers == {"Retry-After": str(errors.RETRY_AFTER_SECONDS)}
    assert errors.method_not_allowed("GET, POST").headers == {"Allow": "GET, POST"}
    assert errors.method_not_allowed(None).headers == {}
