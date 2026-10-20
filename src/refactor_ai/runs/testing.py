"""Test support: a scripted stand-in for the workflow coordinator.

ScriptedWorkflow has the run_workflow signature, never calls a model and never executes
code. Tests use it to drive the run service through chosen status sequences, outcomes,
exceptions and pauses. Like FakeProvider, it is not evidence of model behavior.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence

from refactor_ai.contracts import (
    Disposition,
    ModelReviewResult,
    ReferenceRunner,
    ReferenceTestsResult,
    RubricCheck,
    RunStatus,
    StatusCallback,
    SyntaxCheck,
    VerificationResult,
    WorkflowOutcome,
    WorkflowRequest,
    WorkflowSettings,
)
from refactor_ai.providers.base import Provider
from refactor_ai.providers.fake import FAKE_MODEL, FAKE_PREFIX
from refactor_ai.tasks import guard_clauses

MULTI_ROLE_STATUSES = (
    RunStatus.ANALYZING,
    RunStatus.GENERATING,
    RunStatus.VERIFYING,
    RunStatus.COMPLETED,
)

OutcomeFactory = Callable[[WorkflowRequest, Provider, WorkflowSettings], WorkflowOutcome]


_CHECKS = {
    # disposition: (rubric, reference tests, model review)
    Disposition.PROPOSAL_READY: ("pass", "pass", "accept"),
    Disposition.UNCERTAIN: ("pass", "not_available", "not_run"),
    Disposition.REJECTED: ("fail", "not_run", "reject"),
}


def scripted_outcome(
    request: WorkflowRequest,
    provider: Provider,
    settings: WorkflowSettings,
    disposition: Disposition = Disposition.PROPOSAL_READY,
) -> WorkflowOutcome:
    """A completed outcome; the proposal is the deterministic reference transformation."""
    if disposition == Disposition.NO_CHANGE:
        return WorkflowOutcome(
            status=RunStatus.COMPLETED,
            provider_mode=provider.mode,
            verification=VerificationResult(
                syntax=SyntaxCheck(status="not_run"),
                rubric=RubricCheck(status="not_run"),
                reference_tests=ReferenceTestsResult(status="not_run"),
                model_review=ModelReviewResult(status="not_run"),
                disposition=Disposition.NO_CHANGE,
                disposition_reasons=["no_opportunity"],
            ),
            stop_reason="no_change",
        )
    rubric, tests, review = _CHECKS[disposition]
    case_id = None if request.reference_case is None else request.reference_case.case_id
    return WorkflowOutcome(
        status=RunStatus.COMPLETED,
        provider_mode=provider.mode,
        model=FAKE_MODEL if provider.mode == "fake" else None,
        proposed_code=guard_clauses.to_guard_clauses(request.code) or request.code,
        explanation=f"{FAKE_PREFIX} scripted workflow outcome for tests.",
        verification=VerificationResult(
            syntax=SyntaxCheck(status="pass"),
            rubric=RubricCheck(status=rubric),
            reference_tests=ReferenceTestsResult(status=tests, case_id=case_id),
            model_review=ModelReviewResult(status=review),
            disposition=disposition,
        ),
        attempt_count=1,
        call_count=1 if settings.mode == "single_role" else 3,
        stop_reason="completed",
    )


class ScriptedWorkflow:
    """Callable like refactor_ai.agents.coordinator.run_workflow.

    statuses are reported through on_status in order; after each one, on_step (if
    given) is called with it. If gate is set, the call then waits for it (a test
    releases it) and fails with TimeoutError when it is not released in gate_timeout_s.
    Finally it raises error, returns outcome(request, provider, settings), or returns a
    scripted proposal_ready outcome. calls, active and max_active record usage.
    """

    def __init__(
        self,
        *,
        statuses: Sequence[RunStatus | str] = MULTI_ROLE_STATUSES,
        outcome: OutcomeFactory | WorkflowOutcome | None = None,
        error: BaseException | None = None,
        gate: threading.Event | None = None,
        gate_timeout_s: float = 10.0,
        delay_s: float = 0.0,
        on_step: Callable[[RunStatus | str], None] | None = None,
    ) -> None:
        self.statuses = list(statuses)
        self.outcome = outcome
        self.error = error
        self.gate = gate
        self.gate_timeout_s = gate_timeout_s
        self.delay_s = delay_s
        self.on_step = on_step
        self.calls: list[WorkflowRequest] = []
        self.settings_seen: list[WorkflowSettings] = []
        self.runners_seen: list[ReferenceRunner | None] = []
        self.active = 0
        self.max_active = 0
        self.entered = threading.Event()
        self._lock = threading.Lock()

    def __call__(
        self,
        request: WorkflowRequest,
        *,
        provider: Provider,
        settings: WorkflowSettings,
        runner: ReferenceRunner | None = None,
        on_status: StatusCallback | None = None,
    ) -> WorkflowOutcome:
        with self._lock:
            self.calls.append(request)
            self.settings_seen.append(settings)
            self.runners_seen.append(runner)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        self.entered.set()
        try:
            for status in self.statuses:
                if on_status is not None:
                    on_status(status)  # type: ignore[arg-type]
                if self.on_step is not None:
                    self.on_step(status)
            if self.delay_s:
                time.sleep(self.delay_s)
            if self.gate is not None and not self.gate.wait(self.gate_timeout_s):
                raise TimeoutError("The test did not release the workflow gate")
            if self.error is not None:
                raise self.error
            if isinstance(self.outcome, WorkflowOutcome):
                return self.outcome
            if self.outcome is not None:
                return self.outcome(request, provider, settings)
            return scripted_outcome(request, provider, settings)
        finally:
            with self._lock:
                self.active -= 1
