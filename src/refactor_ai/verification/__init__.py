"""Verification of proposals: syntax, task rubric, trusted reference tests, disposition.

The service loads create_runner() from this package. Nothing here executes candidate
code in the calling process; reference tests run only in the runner's separate process.
"""

from refactor_ai.verification.checks import (
    DeterministicChecks,
    check_rubric,
    check_syntax,
    describe_checks,
    run_checks,
    run_reference_tests,
)
from refactor_ai.verification.diffing import changed_lines, unified_diff
from refactor_ai.verification.disposition import decide, not_run_verification, verification_result
from refactor_ai.verification.registry import (
    CaseRegistry,
    RegistryError,
    code_matches_case,
    load_cases,
)
from refactor_ai.verification.runner import RunnerLimits, SubprocessReferenceRunner, create_runner

__all__ = [
    "CaseRegistry",
    "DeterministicChecks",
    "RegistryError",
    "RunnerLimits",
    "SubprocessReferenceRunner",
    "changed_lines",
    "check_rubric",
    "check_syntax",
    "code_matches_case",
    "create_runner",
    "decide",
    "describe_checks",
    "load_cases",
    "not_run_verification",
    "run_checks",
    "run_reference_tests",
    "unified_diff",
    "verification_result",
]
