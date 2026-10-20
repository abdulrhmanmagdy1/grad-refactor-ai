"""Overall disposition derived from separate check results, in the contract's order.

1. failed: the workflow could not produce a proposal (decided by the coordinator).
2. no_change: the input is outside the task scope (decided by the coordinator).
3. rejected: syntax fails, the rubric fails, reference tests fail or error, or the model
   review rejects. A model verdict never overrides a failed deterministic check.
4. uncertain: the review is uncertain, errored or (multi-role) did not run, reference
   tests are not_available or not_run, or a deterministic check did not run.
5. proposal_ready: syntax and rubric pass, reference tests pass, and the review accepts
   (multi-role) or is not_run (single-role).

Missing tests never count as a pass. Every reason is "<code>: <sentence>" so the
interface can show the sentence and evaluation scripts can count the code.
"""

from __future__ import annotations

from refactor_ai.contracts import (
    Disposition,
    ModelReviewResult,
    ReferenceTestsResult,
    RubricCheck,
    SyntaxCheck,
    VerificationResult,
    WorkflowMode,
)

MAX_REASON_CHARS = 400
NO_PROPOSAL = "No proposal to test."

# Reason codes used in VerificationResult.disposition_reasons.
SYNTAX_FAIL = "syntax_fail"
RUBRIC_FAIL = "rubric_fail"
TESTS_FAIL = "tests_fail"
TESTS_ERROR = "tests_error"
REVIEW_REJECT = "review_reject"
REVIEW_UNCERTAIN = "review_uncertain"
REVIEW_ERROR = "review_error"
REVIEW_NOT_RUN = "review_not_run"
TESTS_NOT_AVAILABLE = "tests_not_available"
TESTS_NOT_RUN = "tests_not_run"
CHECK_NOT_RUN = "check_not_run"
READY = "ready"

REASON_CODES = frozenset(
    {
        SYNTAX_FAIL,
        RUBRIC_FAIL,
        TESTS_FAIL,
        TESTS_ERROR,
        REVIEW_REJECT,
        REVIEW_UNCERTAIN,
        REVIEW_ERROR,
        REVIEW_NOT_RUN,
        TESTS_NOT_AVAILABLE,
        TESTS_NOT_RUN,
        CHECK_NOT_RUN,
        READY,
    }
)


def reason(code: str, text: str) -> str:
    """One disposition reason: a machine-readable code and a bounded sentence."""
    sentence = " ".join(text.split())
    if len(sentence) > MAX_REASON_CHARS:
        sentence = sentence[: MAX_REASON_CHARS - 3] + "..."
    return f"{code}: {sentence}"


def tests_passed(tests: ReferenceTestsResult) -> bool:
    """A pass counts only when at least one test ran and every test passed."""
    return tests.status == "pass" and bool(tests.total) and tests.passed == tests.total


def _tests_failed_text(tests: ReferenceTestsResult) -> str:
    if tests.failed is not None and tests.total:
        return f"{tests.failed} of {tests.total} reference tests failed."
    return "The reference tests failed."


def decide(
    syntax: SyntaxCheck,
    rubric: RubricCheck,
    tests: ReferenceTestsResult,
    review: ModelReviewResult,
    *,
    mode: WorkflowMode,
) -> tuple[Disposition, list[str]]:
    """Disposition and reasons for a proposal that exists (rules 3 to 5)."""
    rejected: list[str] = []
    if syntax.status == "fail":
        rejected.append(reason(SYNTAX_FAIL, f"The proposal is not valid Python ({syntax.error})."))
    if rubric.status == "fail":
        details = "; ".join(rubric.reasons) or "a rubric check failed"
        rejected.append(reason(RUBRIC_FAIL, f"The task rubric failed: {details}"))
    if tests.status == "fail":
        rejected.append(reason(TESTS_FAIL, _tests_failed_text(tests)))
    if tests.status == "error":
        detail = tests.reason or "the runner reported an error"
        rejected.append(reason(TESTS_ERROR, f"The reference tests could not complete: {detail}"))
    if review.status == "reject":
        rejected.append(reason(REVIEW_REJECT, "The model review rejected the proposal."))
    if rejected:
        return Disposition.REJECTED, rejected

    uncertain: list[str] = []
    if syntax.status != "pass":
        uncertain.append(reason(CHECK_NOT_RUN, "The syntax check did not run."))
    if rubric.status != "pass":
        uncertain.append(reason(CHECK_NOT_RUN, "The task rubric did not run."))
    if review.status == "uncertain":
        uncertain.append(reason(REVIEW_UNCERTAIN, "The model review was uncertain."))
    elif review.status == "error":
        detail = review.error or "its output could not be used"
        uncertain.append(reason(REVIEW_ERROR, f"The model review failed: {detail}"))
    elif review.status == "not_run" and mode == WorkflowMode.MULTI_ROLE:
        uncertain.append(reason(REVIEW_NOT_RUN, "The model review did not run."))
    if tests.status == "not_available":
        detail = tests.reason or "no reference tests exist for this input"
        uncertain.append(reason(TESTS_NOT_AVAILABLE, f"Behavior was not tested: {detail}"))
    elif tests.status == "not_run":
        detail = tests.reason or "the reference tests were not executed"
        uncertain.append(reason(TESTS_NOT_RUN, f"Behavior was not tested: {detail}"))
    elif not tests_passed(tests):
        uncertain.append(
            reason(
                TESTS_NOT_AVAILABLE,
                "The reference test result reports no completed passing tests.",
            )
        )
    if uncertain:
        return Disposition.UNCERTAIN, uncertain

    review_text = (
        "the model review accepted it"
        if review.status == "accept"
        else "no model review is part of the single-role workflow"
    )
    return Disposition.PROPOSAL_READY, [
        reason(
            READY,
            f"Syntax and rubric passed, {tests.passed} of {tests.total} reference tests "
            f"passed and {review_text}. Passing tests does not prove equal behavior for "
            "every input.",
        )
    ]


def verification_result(
    syntax: SyntaxCheck,
    rubric: RubricCheck,
    tests: ReferenceTestsResult,
    review: ModelReviewResult,
    *,
    mode: WorkflowMode,
) -> VerificationResult:
    disposition, reasons = decide(syntax, rubric, tests, review, mode=mode)
    return VerificationResult(
        syntax=syntax,
        rubric=rubric,
        reference_tests=tests,
        model_review=review,
        disposition=disposition,
        disposition_reasons=reasons,
    )


def not_run_verification(
    disposition: Disposition,
    reasons: list[str],
    *,
    syntax: SyntaxCheck | None = None,
    rubric: RubricCheck | None = None,
    tests: ReferenceTestsResult | None = None,
    review: ModelReviewResult | None = None,
) -> VerificationResult:
    """Verification for a no_change or failed outcome; missing dimensions are not_run."""
    if disposition not in (Disposition.NO_CHANGE, Disposition.FAILED):
        raise ValueError("Only no_change and failed outcomes skip the disposition rules")
    return VerificationResult(
        syntax=syntax or SyntaxCheck(status="not_run"),
        rubric=rubric or RubricCheck(status="not_run"),
        reference_tests=tests or ReferenceTestsResult(status="not_run", reason=NO_PROPOSAL),
        model_review=review or ModelReviewResult(status="not_run"),
        disposition=disposition,
        disposition_reasons=list(reasons),
    )
