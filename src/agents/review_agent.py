"""Review Agent: deterministic three-layer verification (FR04, NFR01, NFR02, NFR06, Phase 3).

Layers:

1. **Static layer** — syntax validity, symbol preservation, caller-compatible
   signatures, and real before/after metric snapshots with signed deltas.
2. **Behavioural layer** — user-supplied tests when provided; otherwise the
   AutoTestSynthesizer builds golden-baseline tests that compare the candidate
   against the original implementation on sampled inputs. Everything runs in
   the isolated sandbox subprocess; the API process never executes code.
3. **Verdict layer** — ``approved`` / ``rejected`` / ``uncertain`` with
   actionable ``critique_feedback`` consumed by the Refactoring Agent on retry.
"""

import ast

from core.ast_analyzer import analyze
from core.diff_utils import (
    extract_symbol_signatures,
    extract_top_level_symbols,
    generate_diff,
)
from core.schemas import DiffOutput, VerificationResult
from runner.sandbox import IsolatedRunner, sandbox_runner
from runner.test_generator import AutoTestSynthesizer

_DELTA_KEYS = (
    "loc",
    "functions_count",
    "classes_count",
    "async_functions_count",
    "total_cyclomatic_complexity",
    "max_cyclomatic_complexity",
    "cognitive_complexity_total",
    "max_cognitive_complexity",
    "maintainability_index",
)
_HALSTEAD_DELTA_KEYS = ("volume", "difficulty", "effort", "estimated_bugs")

_MI_REGRESSION_POINTS = 3.0
_MI_REGRESSION_RELATIVE = 0.10


class ReviewAgent:
    """Agent responsible for deterministic verification of refactoring candidates."""

    def __init__(
        self,
        runner: IsolatedRunner | None = None,
        synthesizer: AutoTestSynthesizer | None = None,
    ) -> None:
        self.runner = runner or sandbox_runner
        self.synthesizer = synthesizer or AutoTestSynthesizer()

    def review(
        self,
        original_code: str,
        candidate_code: str,
        test_code: str | None = None,
        findings: list | None = None,
        timeout: float | None = None,
    ) -> tuple[VerificationResult, DiffOutput, str | None]:
        """Verify a candidate and return (verification, diff, auto_test_source)."""
        diff_output = generate_diff(original_code, candidate_code)
        details: dict[str, object] = {
            "added_lines": diff_output.added_lines,
            "removed_lines": diff_output.removed_lines,
            "modified_components": diff_output.modified_components,
        }

        # ------------------------------------------------------------------ #
        # Layer 1a: syntax validity
        # ------------------------------------------------------------------ #
        syntax_valid = True
        syntax_error_msg: str | None = None
        try:
            ast.parse(candidate_code)
        except (SyntaxError, ValueError) as exc:
            syntax_valid = False
            syntax_error_msg = str(exc)
            details["syntax_error"] = syntax_error_msg

        if not syntax_valid:
            return (
                VerificationResult(
                    syntax_valid=False,
                    tests_available=bool(test_code),
                    tests_passed=False,
                    review_verdict="rejected",
                    review_notes=(
                        f"Candidate code contains invalid Python syntax: {syntax_error_msg}"
                    ),
                    preserved_symbols=False,
                    critique_feedback=(
                        "The previous candidate did not parse as Python. Return a complete, "
                        "syntactically valid module with the same top-level structure."
                    ),
                    details=details,
                ),
                diff_output,
                None,
            )

        # ------------------------------------------------------------------ #
        # Layer 1b: symbol preservation + caller-compatible signatures
        # ------------------------------------------------------------------ #
        orig_symbols = extract_top_level_symbols(original_code)
        cand_symbols = extract_top_level_symbols(candidate_code)
        missing_symbols = orig_symbols - cand_symbols
        preserved_symbols = len(missing_symbols) == 0
        details["missing_symbols"] = sorted(missing_symbols)

        if not preserved_symbols:
            return (
                VerificationResult(
                    syntax_valid=True,
                    tests_available=bool(test_code),
                    tests_passed=False,
                    review_verdict="rejected",
                    review_notes=(
                        "Refactored code removed required function/class definitions: "
                        f"{sorted(missing_symbols)}"
                    ),
                    preserved_symbols=False,
                    critique_feedback=(
                        "The candidate dropped these definitions: "
                        f"{sorted(missing_symbols)}. Restore every original function and "
                        "class with its exact name; helpers may only be added."
                    ),
                    details=details,
                ),
                diff_output,
                None,
            )

        signature_violations = self._signature_violations(original_code, candidate_code)
        details["signature_violations"] = signature_violations
        if signature_violations:
            return (
                VerificationResult(
                    syntax_valid=True,
                    tests_available=bool(test_code),
                    tests_passed=False,
                    review_verdict="rejected",
                    review_notes=(
                        "Refactored code changed call-compatible signatures: "
                        + "; ".join(signature_violations)
                    ),
                    preserved_symbols=True,
                    critique_feedback=(
                        "Keep every existing parameter name and ordering unchanged: "
                        + "; ".join(signature_violations)
                    ),
                    details=details,
                ),
                diff_output,
                None,
            )

        # ------------------------------------------------------------------ #
        # Layer 1c: real metric snapshots and signed deltas
        # ------------------------------------------------------------------ #
        before = analyze(original_code)
        after = analyze(candidate_code)
        metrics_before = dict(before.metrics)
        metrics_after = dict(after.metrics)
        metrics_delta = self._metric_delta(metrics_before, metrics_after)

        before_rules = {finding.rule for finding in before.findings}
        after_rules = {finding.rule for finding in after.findings}
        resolved_rules = sorted(before_rules - after_rules)
        remaining_rules = sorted(after_rules)
        requested_rules = {
            getattr(finding, "rule", None)
            or (finding.get("rule") if isinstance(finding, dict) else None)
            for finding in (findings or [])
        }
        requested_rules.discard(None)
        if not requested_rules:
            # No explicit request from the orchestrator: treat the findings of
            # the original module as the target, which is what the user sees.
            requested_rules = set(before_rules)
        unresolved_requested = sorted(requested_rules & after_rules)
        details["resolved_findings"] = resolved_rules
        details["remaining_findings"] = remaining_rules
        details["requested_findings"] = sorted(requested_rules)
        details["unresolved_requested_findings"] = unresolved_requested

        # A syntactic no-op is not a successful refactoring merely because it
        # parses and passes tests. AST equality (ignoring comments/formatting)
        # is the strict, deterministic definition used here; partial rewrites
        # are still measured separately by the evaluation harness through
        # ``smell_rule_resolved`` and the composite ``refactor_success`` flag.
        if requested_rules and self._ast_equivalent(original_code, candidate_code):
            return (
                VerificationResult(
                    syntax_valid=True,
                    tests_available=bool(test_code and test_code.strip()),
                    tests_passed=False,
                    review_verdict="rejected",
                    review_notes=(
                        "The candidate is AST-identical to the original; no requested "
                        "finding was addressed: " + ", ".join(sorted(requested_rules))
                    ),
                    preserved_symbols=True,
                    critique_feedback=(
                        "The output is the original module unchanged. Apply a real "
                        "refactoring for the detected finding (extract a helper, merge "
                        "nested conditions, replace the broad exception handler, and so "
                        "on) while keeping every symbol and signature unchanged."
                    ),
                    details=details,
                ),
                diff_output,
                None,
            )

        # ------------------------------------------------------------------ #
        # Layer 2: behavioural verification in the isolated sandbox
        # ------------------------------------------------------------------ #
        auto_test_source: str | None = None
        tests_available = bool(test_code and test_code.strip())
        tests_passed = False
        sandbox_result = None

        if tests_available:
            sandbox_result = self.runner.run_test(candidate_code, test_code or "", timeout=timeout)
        else:
            auto_test_source, synthesis_meta = self.synthesizer.synthesize(original_code)
            details["auto_test_synthesis"] = synthesis_meta
            if auto_test_source is not None:
                sandbox_result = self.runner.run_test(
                    candidate_code,
                    auto_test_source,
                    timeout=timeout,
                    reference_code=original_code,
                )
                # Auto tests only exist when the synthesizer found samplable
                # functions; the candidate must pass them.
                tests_available = True

        if sandbox_result is not None:
            tests_passed = sandbox_result.success
            details["sandbox"] = sandbox_result.model_dump()

        base_fields = {
            "syntax_valid": True,
            "tests_available": tests_available,
            "tests_passed": tests_passed,
            "preserved_symbols": True,
            "auto_generated_tests": auto_test_source is not None,
            "metrics_before": metrics_before,
            "metrics_after": metrics_after,
            "metrics_delta": metrics_delta,
        }

        if tests_available and not tests_passed:
            err_diag = (
                sandbox_result.error_message if sandbox_result is not None else "Assertions failed"
            )
            failure_excerpt = self._failure_excerpt(sandbox_result)
            return (
                VerificationResult(
                    **base_fields,
                    review_verdict="rejected",
                    review_notes=f"Isolated test execution failed: {err_diag}",
                    critique_feedback=(
                        "The candidate's behaviour diverged from the original on sampled "
                        f"inputs. Failing output:\n{failure_excerpt}\n"
                        "Keep results, raised exception types, and generator output "
                        "identical for every input."
                    ),
                    details=details,
                ),
                diff_output,
                auto_test_source,
            )

        # ------------------------------------------------------------------ #
        # Layer 3: verdict composition
        # ------------------------------------------------------------------ #
        mi_delta = float(metrics_delta.get("maintainability_index", 0.0))
        mi_before_value = float(metrics_before.get("maintainability_index") or 0.0)
        relative_drop = abs(mi_delta) / mi_before_value if mi_before_value else 0.0
        if (
            tests_available
            and mi_delta < -_MI_REGRESSION_POINTS
            and relative_drop > _MI_REGRESSION_RELATIVE
        ):
            return (
                VerificationResult(
                    **base_fields,
                    review_verdict="uncertain",
                    review_notes=(
                        "Candidate passed all executable checks, but Maintainability "
                        f"Index regressed by {abs(mi_delta)} points "
                        f"({relative_drop:.1%} relative loss, "
                        f"{metrics_before.get('maintainability_index')} -> "
                        f"{metrics_after.get('maintainability_index')})."
                    ),
                    critique_feedback=(
                        "Behaviour matched, but the structure got measurably worse: "
                        f"Maintainability Index fell by {abs(mi_delta)} points. "
                        "Produce a variant that improves or preserves maintainability."
                    ),
                    details=details,
                ),
                diff_output,
                auto_test_source,
            )

        notes = "Syntax is valid, core symbols are preserved, and signatures stay call-compatible"
        if tests_available and auto_test_source is not None:
            notes += (
                ", and auto-synthesized golden equivalence tests passed in the isolated "
                "sandbox (sampled inputs only, not a full proof)."
            )
        elif tests_available:
            notes += ", and reference tests passed successfully in isolated sandbox."
        else:
            notes += ". (No behavioural tests were available: no user tests were supplied.)"

        return (
            VerificationResult(
                **base_fields,
                review_verdict="approved",
                review_notes=notes,
                details=details,
            ),
            diff_output,
            auto_test_source,
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _ast_equivalent(left: str, right: str) -> bool:
        """Compare semantics while ignoring comments and formatting."""
        try:
            left_tree = ast.parse(left)
            right_tree = ast.parse(right)
        except (SyntaxError, ValueError):
            return False
        return ast.dump(left_tree, include_attributes=False) == ast.dump(
            right_tree, include_attributes=False
        )

    @staticmethod
    def _signature_violations(original_code: str, candidate_code: str) -> list[str]:
        original = extract_symbol_signatures(original_code)
        candidate = extract_symbol_signatures(candidate_code)
        violations: list[str] = []
        for name, expected in original.items():
            actual = candidate.get(name)
            if actual is not None and actual != expected:
                violations.append(f"{name}: expected {expected!r}, got {actual!r}")
        return violations

    @staticmethod
    def _metric_delta(before: dict, after: dict) -> dict[str, float | int | None]:
        delta: dict[str, float | int | None] = {}
        for key in _DELTA_KEYS:
            if key in before and key in after:
                try:
                    delta[key] = round(float(after[key]) - float(before[key]), 3)
                except (TypeError, ValueError):
                    continue
        before_halstead = before.get("halstead") or {}
        after_halstead = after.get("halstead") or {}
        for key in _HALSTEAD_DELTA_KEYS:
            if key in before_halstead and key in after_halstead:
                delta[f"halstead_{key}"] = round(
                    float(after_halstead[key]) - float(before_halstead[key]), 3
                )
        return delta

    @staticmethod
    def _failure_excerpt(sandbox_result) -> str:
        if sandbox_result is None:
            return "(no sandbox output captured)"
        combined = f"{sandbox_result.stdout}\n{sandbox_result.stderr}".strip()
        lines = [line for line in combined.splitlines() if line.strip()]
        return "\n".join(lines[-12:]) if lines else "(empty output)"
