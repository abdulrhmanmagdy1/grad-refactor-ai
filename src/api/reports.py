"""Markdown report rendering for stored runs (FR07 evidence export).

Renders the *stored* run record — the same data the UI shows — into a
portable Markdown document used for the academic report and GitHub Release
notes. Everything is read back from SQLite; the renderer never invents
values, and missing sections are labelled as absent (NFR06).
"""

import json
from datetime import UTC, datetime
from typing import Any

from core.schemas import RunRecord


def _fence(code: str, language: str = "python") -> str:
    """Wrap code in a fence long enough to survive embedded backticks."""
    longest = 0
    current = 0
    for char in code:
        current = current + 1 if char == "`" else 0
        longest = max(longest, current)
    ticks = "`" * max(3, longest + 1)
    return f"{ticks}{language}\n{code.rstrip()}\n{ticks}"


def _fmt(value: Any) -> str:
    """Render a single scalar for a Markdown table cell."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    if isinstance(value, (int, str)):
        return str(value)
    return f"`{json.dumps(value, sort_keys=True)}`"


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def _metrics_table(run: RunRecord) -> str | None:
    """Before / after / delta table over the union of measured metric keys."""
    before = run.metrics_before or {}
    after = run.metrics_after or {}
    delta = run.metrics_delta or {}
    keys: list[str] = []
    for source in (before, after, delta):
        for key in source:
            if key not in keys:
                keys.append(key)
    if not keys:
        return None
    rows = [
        [f"`{key}`", _fmt(before.get(key)), _fmt(after.get(key)), _fmt(delta.get(key))]
        for key in keys
    ]
    return _table(["Metric", "Before", "After", "Δ"], rows)


def render_run_report(run: RunRecord, version: str = "0.1.0") -> str:
    """Render a stored run record as a Markdown report."""
    metrics = run.metrics or {}
    limits = metrics.get("limits") if isinstance(metrics.get("limits"), dict) else {}
    duration = metrics.get("total_duration_ms")
    tokens = metrics.get("total_tokens")
    parts: list[str] = []

    parts.append(f"# Refactoring Run Report — `{run.id}`")
    parts.append(
        "Generated from the stored run record; every value below is measured by the "
        "pipeline or recorded user input, nothing is hand-written (NFR06)."
    )

    tokens_cell = "—"
    if isinstance(tokens, int):
        prompt_tokens = metrics.get("prompt_tokens", 0)
        completion_tokens = metrics.get("completion_tokens", 0)
        tokens_cell = f"{tokens} (prompt {prompt_tokens} + completion {completion_tokens})"
    overview_rows: list[list[Any]] = [
        ["Run ID", f"`{run.id}`"],
        ["Created (UTC)", run.created_at],
        ["Status", f"`{run.status.value}`"],
        ["Refactoring type", run.refactoring_type or "—"],
        ["Provider", metrics.get("provider") or "—"],
        ["Model", metrics.get("model") or "—"],
        ["Retries used", metrics.get("retries_used", "—")],
        [
            "Duration",
            f"{round(float(duration), 2)} ms" if isinstance(duration, (int, float)) else "—",
        ],
        ["Tokens (total)", tokens_cell],
    ]
    if run.verification is not None:
        overview_rows.append(["Review verdict", f"`{run.verification.review_verdict}`"])
    if run.user_feedback:
        comment = f" — “{run.feedback_comment}”" if run.feedback_comment else ""
        overview_rows.append(["User decision", f"`{run.user_feedback}`{comment}"])
    if limits:
        limit_bits = ", ".join(f"{key}={value}" for key, value in limits.items())
        overview_rows.append(["Declared limits", limit_bits])
    parts.append(_table(["Field", "Value"], overview_rows))

    parts.append("## Findings (static AST analysis)")
    if run.findings:
        parts.append(
            _table(
                ["Rule", "Line", "Node", "Message", "Rationale"],
                [
                    [
                        f"`{f.rule}`",
                        f.line if f.end_line is None else f"{f.line}–{f.end_line}",
                        f"`{f.node_type}`",
                        f.message,
                        f.rationale,
                    ]
                    for f in run.findings
                ],
            )
        )
    else:
        parts.append("No findings were recorded for this run (the analysis reported a clean file).")

    parts.append("## Input code")
    parts.append(_fence(run.input_code))

    parts.append("## Proposed refactoring")
    if run.output_code:
        parts.append(_fence(run.output_code))
        if run.explanation:
            parts.append(f"**Explanation.** {run.explanation}")
    else:
        parts.append("No refactored candidate was produced for this run.")

    parts.append("## Diff")
    if run.diff:
        parts.append(_fence(run.diff, language="diff"))
    else:
        parts.append("No diff was recorded for this run.")

    parts.append("## Verification")
    verification = run.verification
    if verification is None:
        parts.append("No verification record was stored for this run.")
    else:
        rows = [
            ["Syntax valid", _fmt(verification.syntax_valid)],
            ["Tests available", _fmt(verification.tests_available)],
            ["Tests passed", _fmt(verification.tests_passed)],
            ["Review verdict", f"`{verification.review_verdict}`"],
            ["Symbols preserved", _fmt(verification.preserved_symbols)],
            ["Auto-generated tests", _fmt(verification.auto_generated_tests)],
        ]
        parts.append(_table(["Check", "Result"], rows))
        parts.append(f"**Review notes.** {verification.review_notes}")
        if verification.critique_feedback:
            parts.append(f"**Critique fed back on retry.** {verification.critique_feedback}")

    metrics_table = _metrics_table(run)
    parts.append("## Metrics (before / after / delta)")
    parts.append(metrics_table or "No software-metrics snapshots were recorded for this run.")

    parts.append("## Agent trace")
    if run.agent_traces:
        trace_rows = []
        for index, trace in enumerate(run.agent_traces, start=1):
            duration_cell = (
                f"{round(trace.duration_ms, 2)} ms"
                if isinstance(trace.duration_ms, (int, float))
                else "—"
            )
            trace_rows.append(
                [index, f"`{trace.agent}`", f"`{trace.phase}`", trace.summary, duration_cell]
            )
        parts.append(_table(["#", "Agent", "Phase", "Summary", "Duration"], trace_rows))
    else:
        parts.append("No agent trace steps were recorded for this run.")

    parts.append("## Auto-generated verification tests")
    if run.auto_generated_tests:
        parts.append(_fence(run.auto_generated_tests))
    else:
        parts.append("No auto-generated tests were stored for this run.")

    if run.errors:
        parts.append("## Errors")
        parts.append(_fence(run.errors, language="text"))

    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    parts.append(
        f"---\n_Report generated at {generated_at} by the Refactor AI API v{version}. "
        "Submitted code is inspected statically; the API process never executes it (NFR01). "
        "Isolated test execution happens only in the sandbox runner._"
    )
    return "\n\n".join(parts) + "\n"
