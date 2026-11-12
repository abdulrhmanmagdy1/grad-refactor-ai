"""Static, execution-free scoring for best-of-N refactoring candidates.

The selector is used at inference time to choose among several samples from
the same model. It never executes candidate code (NFR01); it only parses the
AST and compares findings, symbols, signatures and structural metrics.

Scoring priorities, highest first:

1. syntactically valid Python;
2. all original top-level symbols still present;
3. call-compatible signatures preserved;
4. the requested findings (or, when no findings were supplied, every
   finding detected in the original) actually disappear;
5. lower cyclomatic complexity / higher maintainability, with a guard
   against wild rewrites that change the module beyond recognition.
"""

from __future__ import annotations

import ast
from typing import Any

from core.ast_analyzer import analyze
from core.diff_utils import extract_symbol_signatures, extract_top_level_symbols

_INVALID_SCORE = -10_000.0


def _rules(analysis: Any) -> set[str]:
    return {finding.rule for finding in getattr(analysis, "findings", [])}


def score_candidate(
    original_code: str,
    candidate_code: str,
    findings: list[Any] | None = None,
) -> dict[str, Any]:
    """Return a deterministic score and the evidence behind it."""
    before = analyze(original_code)
    after = analyze(candidate_code)

    original_symbols = extract_top_level_symbols(original_code)
    candidate_symbols = extract_top_level_symbols(candidate_code)
    missing_symbols = sorted(original_symbols - candidate_symbols)
    preserved_symbols = not missing_symbols

    original_signatures = extract_symbol_signatures(original_code)
    candidate_signatures = extract_symbol_signatures(candidate_code)
    signature_violations = [
        f"{name}: expected {expected!r}, got {candidate_signatures.get(name)!r}"
        for name, expected in original_signatures.items()
        if candidate_signatures.get(name) != expected
    ]

    before_rules = _rules(before)
    after_rules = _rules(after)
    requested_rules = {finding.rule for finding in findings or []} or before_rules
    resolved_rules = sorted(requested_rules & (before_rules - after_rules))
    remaining_rules = sorted(requested_rules & after_rules)
    resolution_ratio = len(resolved_rules) / len(requested_rules) if requested_rules else 0.0

    metrics_before = dict(getattr(before, "metrics", {}) or {})
    metrics_after = dict(getattr(after, "metrics", {}) or {})
    complexity_before = float(metrics_before.get("total_cyclomatic_complexity") or 0)
    complexity_after = float(metrics_after.get("total_cyclomatic_complexity") or 0)
    complexity_reduction_pct = (
        (complexity_before - complexity_after) / complexity_before * 100
        if complexity_before
        else 0.0
    )
    mi_before = metrics_before.get("maintainability_index")
    mi_after = metrics_after.get("maintainability_index")
    mi_delta = (
        float(mi_after) - float(mi_before)
        if mi_before is not None and mi_after is not None
        else 0.0
    )

    new_rules = after_rules - before_rules
    length_ratio = len(candidate_code) / max(len(original_code), 1)

    score = 0.0
    if after.syntax_valid:
        score += 100.0
    if preserved_symbols:
        score += 100.0
    if not signature_violations:
        score += 100.0
    score += 200.0 * resolution_ratio
    score += max(-50.0, min(50.0, complexity_reduction_pct))
    score += max(-30.0, min(30.0, mi_delta))
    score -= 25.0 * len(new_rules)
    score -= 20.0 * abs(1.0 - length_ratio)

    if not after.syntax_valid or not preserved_symbols or signature_violations:
        score += _INVALID_SCORE

    return {
        "score": round(score, 4),
        "syntax_valid": bool(after.syntax_valid),
        "preserved_symbols": preserved_symbols,
        "signature_violations": signature_violations,
        "missing_symbols": missing_symbols,
        "requested_rules": sorted(requested_rules),
        "resolved_rules": resolved_rules,
        "remaining_rules": remaining_rules,
        "new_rules": sorted(new_rules),
        "resolution_ratio": round(resolution_ratio, 4),
        "complexity_before": complexity_before,
        "complexity_after": complexity_after,
        "complexity_reduction_pct": round(complexity_reduction_pct, 2),
        "mi_before": mi_before,
        "mi_after": mi_after,
        "mi_delta": round(mi_delta, 4),
        "loc_before": len(original_code.splitlines()),
        "loc_after": len(candidate_code.splitlines()),
        "length_ratio": round(length_ratio, 4),
    }


def select_best_candidate(
    original_code: str,
    candidates: list[str],
    findings: list[Any] | None = None,
) -> tuple[str, int, list[dict[str, Any]]]:
    """Pick the highest-scoring candidate; ties go to the earliest sample."""
    if not candidates:
        return "", -1, []

    scores = [score_candidate(original_code, candidate, findings) for candidate in candidates]
    best_index = max(
        range(len(candidates)),
        key=lambda index: (scores[index]["score"], -index),
    )
    return candidates[best_index], best_index, scores


def is_parseable(code: str) -> bool:
    """Return whether *code* parses, without executing it."""
    try:
        ast.parse(code)
    except (SyntaxError, ValueError):
        return False
    return True
