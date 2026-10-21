"""Tables and figures computed only from retained case-level evaluation records.

Every rate uses the number of attempted cases of that arm as its denominator, so
failures, timeouts and harness exceptions always count against the arm; syntax, rubric
and reference-test successes count only for completed runs. Reference-test pass rates
are also given over the cases whose tests actually executed (at least one test produced
a result; a runner error that ran no test is not an execution). Paired
comparisons use only cases attempted by both arms; exact McNemar p-values (two-sided
binomial test on the discordant pairs) are reported with a Holm adjustment over the
comparisons shown. Small samples support limited conclusions, and passing reference
tests is never treated as proof of equivalence for all inputs.
"""

from __future__ import annotations

import csv
import io
import json
import math
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape

from refactor_ai.evaluation import targets as frozen_targets
from refactor_ai.evaluation.protocol import ARMS
from refactor_ai.evaluation.records import TIMEOUT_FAILURES, RecordFileError, read_jsonl

PAIRS = (("B", "A"), ("C", "A"), ("D", "C"), ("D", "B"))
PAIR_MEANING = {
    ("B", "A"): "role coordination, original model",
    ("C", "A"): "fine-tuning, single role",
    ("D", "C"): "role coordination, adapted refactoring role",
    ("D", "B"): "fine-tuning, multi-role",
}
RATE_METRICS = (
    ("completed", "Run completed"),
    ("failed", "Run failed (any reason)"),
    ("timeouts", "Timed out (provider or run)"),
    ("syntax_valid", "Proposal parses (syntax pass)"),
    ("rubric_pass", "Task rubric pass"),
    ("tests_pass", "Reference tests pass"),
    ("tests_executed", "Reference tests executed"),
    ("proposal_ready", "Overall acceptance (proposal_ready)"),
    ("rejected", "Rejected"),
    ("uncertain", "Uncertain"),
    ("no_change", "No change"),
    ("recheck_disagreement", "Harness recheck disagrees with workflow"),
)
FIGURE_METRICS = (
    ("syntax_valid", "Proposal parses"),
    ("rubric_pass", "Task rubric pass"),
    ("tests_pass", "Reference tests pass"),
    ("proposal_ready", "Overall acceptance (proposal_ready)"),
    ("failed", "Run failed"),
)


class ReportError(ValueError):
    pass


def load_records(paths: list[Path]) -> list[dict]:
    rows = []
    for path in paths:
        try:
            rows += read_jsonl(path)
        except RecordFileError as exc:
            raise ReportError(str(exc)) from exc
    return rows


def _tests_executed(row: dict) -> bool:
    """At least one reference test produced a result. A runner error that ran no test
    (the test process could not start, the runner crashed) is not an execution."""
    tests = row["reference_tests"]
    results = sum(tests.get(key) or 0 for key in ("passed", "failed", "errored"))
    return tests["status"] in ("pass", "fail", "error") and results > 0


def _predicate(name: str, row: dict) -> bool:
    # A failed run has no final proposal: its syntax, rubric and tests never count.
    completed = row["run_status"] == "completed"
    executed = completed and _tests_executed(row)
    return {
        "completed": completed,
        "failed": not completed,
        "timeouts": row["failure_type"] in TIMEOUT_FAILURES,
        "syntax_valid": completed and row["syntax"] == "pass",
        "rubric_pass": completed and row["rubric"] == "pass",
        "tests_pass": executed and row["reference_tests"]["status"] == "pass",
        "tests_executed": executed,
        "proposal_ready": bool(row["proposal_ready"]),
        "rejected": row["disposition"] == "rejected",
        "uncertain": row["disposition"] == "uncertain",
        "no_change": row["disposition"] == "no_change",
        "recheck_disagreement": row["recheck"].get("agrees_with_workflow") is False,
    }[name]


def check_consistency(rows: list[dict]) -> dict:
    if not rows:
        raise ReportError("no evaluation records")
    for key in ("protocol_version", "dataset_sha256", "split", "split_sha256"):
        values = sorted({str(row[key]) for row in rows})
        if len(values) != 1:
            raise ReportError(f"records mix several values of {key}: {values}")
    keys = Counter((row["case_id"], row["arm"]) for row in rows)
    duplicated = sorted(key for key, count in keys.items() if count > 1)
    if duplicated:
        raise ReportError(f"duplicate (case, arm) attempts: {duplicated[:5]}")
    first = rows[0]
    return {
        "protocol_version": first["protocol_version"],
        "protocol_status": sorted({row["protocol_status"] for row in rows}),
        "split": first["split"],
        "split_sha256": first["split_sha256"],
        "dataset_sha256": first["dataset_sha256"],
        "evaluation_ids": sorted({row["evaluation_id"] for row in rows}),
        "provider_modes": sorted({str(row["provider_mode"]) for row in rows}),
        "models": sorted(
            {json.dumps(m, sort_keys=True) for row in rows for m in row["models_used"]}
        ),
        "code_shas": sorted({str(row["code_sha"]) for row in rows}),
        "cases": len({row["case_id"] for row in rows}),
    }


def _nearest_rank(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def arm_metrics(rows: list[dict]) -> dict[str, dict]:
    metrics: dict[str, dict] = {}
    for arm in ARMS:
        arm_rows = [row for row in rows if row["arm"] == arm]
        if not arm_rows:
            continue
        n = len(arm_rows)
        entry: dict = {"attempted": n, "rates": {}}
        for name, _label in RATE_METRICS:
            count = sum(_predicate(name, row) for row in arm_rows)
            entry["rates"][name] = {"numerator": count, "denominator": n, "rate": count / n}
        executed = entry["rates"]["tests_executed"]["numerator"]
        passed = entry["rates"]["tests_pass"]["numerator"]
        entry["tests_pass_of_executed"] = {
            "numerator": passed,
            "denominator": executed,
            "rate": passed / executed if executed else None,
        }
        latencies = [row["latency_s"] for row in arm_rows]
        entry["latency_s"] = {
            "median": _nearest_rank(latencies, 0.5),
            "p90": _nearest_rank(latencies, 0.9),
            "mean": sum(latencies) / n,
            "max": max(latencies),
            "denominator": n,
        }
        calls = [row["call_count"] for row in arm_rows]
        entry["calls"] = {"mean": sum(calls) / n, "max": max(calls), "total": sum(calls)}
        tokens = [
            row["prompt_tokens"] + row["completion_tokens"]
            for row in arm_rows
            if row["prompt_tokens"] is not None and row["completion_tokens"] is not None
        ]
        entry["tokens"] = {
            "records_with_counts": len(tokens),
            "denominator": n,
            "mean": sum(tokens) / len(tokens) if tokens else None,
            "total": sum(tokens) if tokens else None,
        }
        memory = [
            row["worker_peak_rss_mb"] for row in arm_rows if row["worker_peak_rss_mb"] is not None
        ]
        gpu = [
            row["gpu_memory_used_mb"] for row in arm_rows if row["gpu_memory_used_mb"] is not None
        ]
        entry["memory_mb"] = {
            "worker_peak_rss_max": max(memory) if memory else None,
            "worker_peak_rss_records": len(memory),
            "gpu_used_max": max(gpu) if gpu else None,
            "gpu_records": len(gpu),
        }
        entry["failure_types"] = dict(
            sorted(Counter(row["failure_type"] for row in arm_rows).items())
        )
        entry["dispositions"] = dict(
            sorted(Counter(str(row["disposition"]) for row in arm_rows).items())
        )
        entry["budget_warnings"] = sum(
            any(w.startswith(("budget_violation", "adapter_")) for w in row["warnings"])
            for row in arm_rows
        )
        metrics[arm] = entry
    return metrics


def exact_mcnemar(first_only: int, second_only: int) -> float:
    """Two-sided exact McNemar p-value (binomial test on discordant pairs, p = 0.5)."""
    n = first_only + second_only
    if n == 0:
        return 1.0
    k = min(first_only, second_only)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


def holm(pvalues: list[float]) -> list[float]:
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    adjusted = [0.0] * len(pvalues)
    running = 0.0
    m = len(pvalues)
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[index]))
        adjusted[index] = running
    return adjusted


def paired_comparisons(rows: list[dict], metric: str = "proposal_ready") -> list[dict]:
    by_key = {(row["case_id"], row["arm"]): row for row in rows}
    cases = sorted({row["case_id"] for row in rows})
    results = []
    for first, second in PAIRS:
        shared = [c for c in cases if (c, first) in by_key and (c, second) in by_key]
        if not shared:
            continue
        a = [_predicate(metric, by_key[(c, first)]) for c in shared]
        b = [_predicate(metric, by_key[(c, second)]) for c in shared]
        both = sum(x and y for x, y in zip(a, b, strict=True))
        first_only = sum(x and not y for x, y in zip(a, b, strict=True))
        second_only = sum(y and not x for x, y in zip(a, b, strict=True))
        results.append(
            {
                "comparison": f"{first} vs {second}",
                "meaning": PAIR_MEANING[(first, second)],
                "metric": metric,
                "paired_cases": len(shared),
                "both": both,
                f"{first}_only": first_only,
                f"{second}_only": second_only,
                "neither": len(shared) - both - first_only - second_only,
                "rate_first": sum(a) / len(shared),
                "rate_second": sum(b) / len(shared),
                "exact_mcnemar_p": exact_mcnemar(first_only, second_only),
            }
        )
    for result, adjusted in zip(
        results, holm([r["exact_mcnemar_p"] for r in results]), strict=True
    ):
        result["holm_adjusted_p"] = adjusted
    return results


def breakdown(rows: list[dict], dimension: str) -> list[dict]:
    out = []
    for arm in ARMS:
        arm_rows = [row for row in rows if row["arm"] == arm]
        for value in sorted({str(row[dimension]) for row in arm_rows}):
            subset = [row for row in arm_rows if str(row[dimension]) == value]
            ready = sum(bool(row["proposal_ready"]) for row in subset)
            out.append(
                {
                    "arm": arm,
                    "dimension": dimension,
                    "value": value,
                    "proposal_ready": ready,
                    "attempted": len(subset),
                    "rate": ready / len(subset),
                }
            )
    return out


def _pct(numerator: int, denominator: int) -> str:
    return (
        f"{numerator}/{denominator} ({100 * numerator / denominator:.1f}%)"
        if denominator
        else "0/0 (n/a)"
    )


def _fmt(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return lines


def _cost_rows(metrics: dict, arms: list[str]) -> list[list[str]]:
    def cells(getter) -> list[str]:
        return [getter(metrics[arm]) for arm in arms]

    def tokens(entry: dict) -> str:
        item = entry["tokens"]
        return f"{_fmt(item['mean'], 1)} ({item['records_with_counts']}/{item['denominator']})"

    def rss(entry: dict) -> str:
        item = entry["memory_mb"]
        return f"{_fmt(item['worker_peak_rss_max'], 1)} ({item['worker_peak_rss_records']})"

    def gpu(entry: dict) -> str:
        item = entry["memory_mb"]
        return f"{_fmt(item['gpu_used_max'], 0)} ({item['gpu_records']})"

    return [
        ["Latency median (s)", *cells(lambda e: _fmt(e["latency_s"]["median"]))],
        ["Latency p90 (s)", *cells(lambda e: _fmt(e["latency_s"]["p90"]))],
        ["Latency mean (s)", *cells(lambda e: _fmt(e["latency_s"]["mean"]))],
        ["Calls per case (mean)", *cells(lambda e: _fmt(e["calls"]["mean"]))],
        ["Calls (total)", *cells(lambda e: str(e["calls"]["total"]))],
        ["Tokens per case (mean; cases with counts)", *cells(tokens)],
        ["Worker peak RSS MB (max; cases measured)", *cells(rss)],
        ["GPU memory used MB (max; cases measured)", *cells(gpu)],
        ["Budget or adapter warnings", *cells(lambda e: str(e["budget_warnings"]))],
    ]


def _paired_rows(paired: list[dict]) -> list[list[str]]:
    rows = []
    for item in paired:
        first, second = item["comparison"].split(" vs ")
        rows.append(
            [
                item["comparison"],
                item["meaning"],
                str(item["paired_cases"]),
                str(item[first + "_only"]),
                str(item[second + "_only"]),
                str(item["both"]),
                str(item["neither"]),
                f"{item['exact_mcnemar_p']:.4f}",
                f"{item['holm_adjusted_p']:.4f}",
            ]
        )
    return rows


def markdown_summary(meta: dict, metrics: dict, paired: list[dict], by_source: list[dict]) -> str:
    arms = list(metrics)
    lines = ["# Evaluation summary", ""]
    if "fake" in meta["provider_modes"]:
        lines += [
            "> **FAKE PROVIDER: plumbing check only.** These records come from the deterministic "
            "test provider, so they say nothing about model quality.",
            "",
        ]
    lines += [
        f"- Protocol: {meta['protocol_version']} (status: {', '.join(meta['protocol_status'])})",
        f"- Split: {meta['split']} (sha256 {meta['split_sha256']}), {meta['cases']} cases",
        f"- Dataset sha256: {meta['dataset_sha256']}",
        f"- Evaluation ids: {', '.join(meta['evaluation_ids'])}",
        f"- Provider modes: {', '.join(meta['provider_modes'])}",
        f"- Code: {', '.join(meta['code_shas'])}",
        "",
        "Every rate below uses all attempted cases of the arm as its denominator, so "
        "failures and timeouts count against the arm; syntax, rubric and reference-test "
        "successes count only for completed runs. Reference tests count as executed when "
        "at least one test produced a result. Passing reference tests supports "
        "behavior preservation only on the tested inputs.",
        "",
        "## Outcomes by arm",
        "",
    ]
    rows = []
    for name, label in RATE_METRICS:
        rates = [metrics[a]["rates"][name] for a in arms]
        rows.append([label] + [_pct(item["numerator"], item["denominator"]) for item in rates])
    executed = [metrics[a]["tests_pass_of_executed"] for a in arms]
    rows.append(
        ["Reference tests pass, of executed"]
        + [_pct(item["numerator"], item["denominator"]) for item in executed]
    )
    lines += _table(["Measure", *arms], rows)
    lines += ["", "## Cost by arm", ""]
    lines += _table(["Measure", *arms], _cost_rows(metrics, arms))
    lines += ["", "## Failure types by arm", ""]
    for arm in arms:
        parts = ", ".join(f"{k}: {v}" for k, v in metrics[arm]["failure_types"].items())
        lines.append(f"- {arm}: {parts}")
    if paired:
        lines += [
            "",
            "## Paired comparisons (overall acceptance)",
            "",
            "Exact McNemar test on discordant cases; Holm adjustment over the comparisons shown.",
            "",
        ]
        header = ["Comparison", "Effect isolated", "Paired cases", "First only", "Second only"]
        header += ["Both", "Neither", "p (exact)", "p (Holm)"]
        lines += _table(header, _paired_rows(paired))
    if by_source:
        lines += ["", "## Overall acceptance by source", ""]
        source_rows = [
            [item["arm"], item["value"], _pct(item["proposal_ready"], item["attempted"])]
            for item in by_source
        ]
        lines += _table(["Arm", "Source", "Accepted"], source_rows)
    lines.append("")
    return "\n".join(lines)


def metrics_csv(metrics: dict) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["arm", "metric", "numerator", "denominator", "rate"])
    for arm, entry in metrics.items():
        for name, _label in RATE_METRICS:
            item = entry["rates"][name]
            writer.writerow(
                [arm, name, item["numerator"], item["denominator"], f"{item['rate']:.6f}"]
            )
        item = entry["tests_pass_of_executed"]
        rate = "" if item["rate"] is None else f"{item['rate']:.6f}"
        writer.writerow(
            [arm, "tests_pass_of_executed", item["numerator"], item["denominator"], rate]
        )
        for stat in ("median", "p90", "mean", "max"):
            value = entry["latency_s"][stat]
            writer.writerow(
                [arm, f"latency_s_{stat}", "", entry["latency_s"]["denominator"], f"{value:.6f}"]
            )
        calls = entry["calls"]
        writer.writerow(
            [arm, "calls_mean", calls["total"], entry["attempted"], f"{calls['mean']:.6f}"]
        )
        tokens = entry["tokens"]
        total = "" if tokens["total"] is None else tokens["total"]
        mean = "" if tokens["mean"] is None else f"{tokens['mean']:.6f}"
        writer.writerow([arm, "tokens_mean", total, tokens["records_with_counts"], mean])
    return buffer.getvalue()


def rows_csv(items: list[dict]) -> str:
    buffer = io.StringIO()
    if not items:
        return ""
    fields = list(dict.fromkeys(key for item in items for key in item))
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for item in items:
        writer.writerow({k: (f"{v:.6f}" if isinstance(v, float) else v) for k, v in item.items()})
    return buffer.getvalue()


# --- Figures (dependency-free SVG; one series per panel, arms on the category axis) -----

FAKE_NOTE = "Fake provider: plumbing check only, not model evidence."
_SVG_STYLE = """
  .surface { fill: #fcfcfb; }
  .bar { fill: #2a78d6; }
  .grid { stroke: #e1e0d9; stroke-width: 1; }
  .axis { stroke: #c3c2b7; stroke-width: 1; }
  .range { stroke: #2a78d6; stroke-width: 2; stroke-linecap: round; }
  .dot { fill: #2a78d6; stroke: #fcfcfb; stroke-width: 2; }
  .title { fill: #0b0b0b; font: 600 14px system-ui, -apple-system, "Segoe UI", sans-serif; }
  .panel { fill: #0b0b0b; font: 600 12px system-ui, -apple-system, "Segoe UI", sans-serif; }
  .label { fill: #52514e; font: 12px system-ui, -apple-system, "Segoe UI", sans-serif; }
  .value { fill: #0b0b0b; font: 12px system-ui, -apple-system, "Segoe UI", sans-serif; }
  .tick { fill: #898781; font: 11px system-ui, -apple-system, "Segoe UI", sans-serif; }
  .warn { fill: #52514e; font: italic 12px system-ui, -apple-system, "Segoe UI", sans-serif; }
  @media (prefers-color-scheme: dark) {
    .surface { fill: #1a1a19; }
    .bar { fill: #3987e5; }
    .grid { stroke: #2c2c2a; }
    .axis { stroke: #383835; }
    .range { stroke: #3987e5; }
    .dot { fill: #3987e5; stroke: #1a1a19; }
    .title, .panel, .value { fill: #ffffff; }
    .label, .warn { fill: #c3c2b7; }
  }
"""


def _text(cls: str, x: float, y: float, content: str, anchor: str | None = None) -> str:
    extra = f' text-anchor="{anchor}"' if anchor else ""
    return f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}"{extra}>{escape(content)}</text>'


def _line(cls: str, x1: float, y1: float, x2: float, y2: float) -> str:
    return f'<line class="{cls}" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"/>'


def _bar_path(x0: float, y: float, width: float, height: float, radius: float = 4.0) -> str:
    """Bar from the baseline with a rounded data end (right) and a square baseline end."""
    if width <= 0:
        return ""
    r = min(radius, width, height / 2)
    x1 = x0 + width
    return (
        f"M{x0:.1f},{y:.1f} H{x1 - r:.1f} Q{x1:.1f},{y:.1f} {x1:.1f},{y + r:.1f} "
        f"V{y + height - r:.1f} Q{x1:.1f},{y + height:.1f} {x1 - r:.1f},{y + height:.1f} "
        f"H{x0:.1f} Z"
    )


def _svg(width: int, height: int, title: str, body: list[str]) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">\n'
        f"<title>{escape(title)}</title>\n<style>{_SVG_STYLE}</style>\n"
        f'<rect class="surface" x="0" y="0" width="{width}" height="{height}"/>\n'
        + "\n".join(body)
        + "\n</svg>\n"
    )


def outcome_figure(metrics: dict, meta: dict) -> str:
    arms = list(metrics)
    width, left, right = 760, 140, 190
    plot = width - left - right
    bar_h, gap, panel_head = 18, 10, 28
    panel_h = panel_head + len(arms) * (bar_h + gap) + 14
    fake = "fake" in meta["provider_modes"]
    top = 64 if fake else 44
    height = top + panel_h * len(FIGURE_METRICS) + 10
    title = f"Outcome rates by arm ({meta['split']} split, {meta['protocol_version']})"
    body = [_text("title", 16, 26, title)]
    if fake:
        body.append(_text("warn", 16, 46, FAKE_NOTE))
    for index, (name, label) in enumerate(FIGURE_METRICS):
        y0 = top + index * panel_h
        body.append(_text("panel", 16, y0 + 16, label))
        plot_top = y0 + panel_head - 4
        plot_bottom = y0 + panel_head + len(arms) * (bar_h + gap) - gap + 4
        for tick in (0, 25, 50, 75, 100):
            x = left + plot * tick / 100
            body.append(_line("grid", x, plot_top, x, plot_bottom))
            if index == len(FIGURE_METRICS) - 1:
                body.append(_text("tick", x, plot_bottom + 14, f"{tick}%", "middle"))
        body.append(_line("axis", left, plot_top, left, plot_bottom))
        for row, arm in enumerate(arms):
            item = metrics[arm]["rates"][name]
            y = y0 + panel_head + row * (bar_h + gap)
            bar_w = plot * item["rate"]
            value = _pct(item["numerator"], item["denominator"])
            body.append(_text("label", left - 10, y + 13, f"Arm {arm}", "end"))
            path = _bar_path(left, y, bar_w, bar_h)
            if path:
                tip = escape(f"Arm {arm}: {label} {value}")
                body.append(f'<path class="bar" d="{path}"><title>{tip}</title></path>')
            body.append(_text("value", left + bar_w + 8, y + 13, value))
    return _svg(width, height, title, body)


def _nice_max(value: float) -> float:
    if value <= 0:
        return 1.0
    magnitude = 10 ** math.floor(math.log10(value))
    for step in (1, 2, 2.5, 5, 10):
        if value <= step * magnitude:
            return step * magnitude
    return 10 * magnitude


def latency_figure(rows: list[dict], metrics: dict, meta: dict) -> str:
    arms = list(metrics)
    width, left, right = 760, 140, 230
    plot = width - left - right
    fake = "fake" in meta["provider_modes"]
    row_h, top = 34, (70 if fake else 50)
    height = top + row_h * len(arms) + 40
    stats = {}
    for arm in arms:
        values = [row["latency_s"] for row in rows if row["arm"] == arm]
        stats[arm] = tuple(_nearest_rank(values, q) for q in (0.1, 0.5, 0.9))
    limit = _nice_max(max(s[2] for s in stats.values()))
    title = f"Latency per case by arm (median and 10th-90th percentile; {meta['split']} split)"
    body = [_text("title", 16, 26, title)]
    if fake:
        body.append(_text("warn", 16, 46, FAKE_NOTE))
    plot_top, plot_bottom = top - 8, top + row_h * len(arms) - 8
    for i in range(5):
        x = left + plot * i / 4
        body.append(_line("grid", x, plot_top, x, plot_bottom))
        body.append(_text("tick", x, plot_bottom + 16, f"{limit * i / 4:g} s", "middle"))
    body.append(_line("axis", left, plot_top, left, plot_bottom))
    for index, arm in enumerate(arms):
        low, mid, high = stats[arm]
        y = top + index * row_h + 6
        x_low, x_mid, x_high = (left + plot * v / limit for v in (low, mid, high))
        text = f"median {mid:.2f} s, p90 {high:.2f} s (n={metrics[arm]['attempted']})"
        body.append(_text("label", left - 10, y + 4, f"Arm {arm}", "end"))
        body.append(_line("range", x_low, y, x_high, y))
        tip = escape(f"Arm {arm}: {text}")
        body.append(
            f'<circle class="dot" cx="{x_mid:.1f}" cy="{y:.1f}" r="5"><title>{tip}</title></circle>'
        )
        body.append(_text("value", left + plot + 12, y + 4, text))
    return _svg(width, height, title, body)


def targets_section(assessment: dict, freeze: dict) -> str:
    """Markdown for the assessment of a protocol freeze record's numerical targets."""
    lines = [
        "## Pre-registered targets",
        "",
        f"Targets of protocol {freeze.get('protocol_version')} (frozen on "
        f"{freeze.get('frozen_on')}), set from the validation baseline before any test-split "
        f"run. Rule: {assessment['rule']}",
        "",
    ]
    rows = []
    for row in assessment["arms"]:
        sign = ">=" if row["kind"] == "floor" else "<="
        measured = "not run" if row["rate"] is None else _pct(row["numerator"], row["denominator"])
        met = {True: "met", False: "not met", None: "n/a"}[row["met"]]
        rows.append(
            [row["arm"], row["metric"], f"{sign} {100 * row['limit_rate']:.2f}%", measured, met]
        )
    lines += _table(["Arm", "Measure", "Target", "Measured", "Result"], rows)
    lines += ["", "Expected directions (Holm-adjusted exact McNemar, alpha 0.05):", ""]
    direction_rows = []
    for item in assessment["comparisons"]:
        first, second = item["comparison"].split(" vs ")
        names = {"first": f"{first} accepts more", "second": f"{second} accepts more"}
        names["none"] = "none"
        observed = "not measured" if item["observed"] is None else names[item["observed"]]
        direction_rows.append(
            [item["comparison"], names[item["expected"]], observed, item["outcome"]]
        )
    lines += _table(["Comparison", "Expected", "Observed", "Result"], direction_rows)
    return "\n".join(lines) + "\n"


def build_report(rows: list[dict], out_dir: Path, freeze: dict | None = None) -> dict[str, str]:
    """Write summary.md, CSV tables and SVG figures; returns written paths.

    With a protocol freeze record (freeze), the report also assesses its numerical
    targets (targets.csv, target_directions.csv, a summary section and report.json
    "targets").
    """
    meta = check_consistency(rows)
    metrics = arm_metrics(rows)
    paired = paired_comparisons(rows)
    by_source = breakdown(rows, "source")
    summary = markdown_summary(meta, metrics, paired, by_source)
    assessment = None
    if freeze is not None:
        if "targets" not in freeze:
            raise ReportError("the protocol freeze record has no numerical targets")
        assessment = frozen_targets.assess(freeze["targets"], metrics, paired)
        summary += "\n" + targets_section(assessment, freeze)
    files = {
        "summary.md": summary,
        "arm_metrics.csv": metrics_csv(metrics),
        "paired.csv": rows_csv(paired),
        "by_source.csv": rows_csv(by_source),
        "by_failure_type.csv": rows_csv(breakdown(rows, "failure_type")),
        "by_source_group.csv": rows_csv(breakdown(rows, "source_group")),
        "report.json": json.dumps(
            {"meta": meta, "metrics": metrics, "paired": paired}
            | ({"targets": assessment} if assessment is not None else {}),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        "figures/outcome_rates.svg": outcome_figure(metrics, meta),
        "figures/latency.svg": latency_figure(rows, metrics, meta),
    }
    if assessment is not None:
        files["targets.csv"] = rows_csv(assessment["arms"])
        files["target_directions.csv"] = rows_csv(assessment["comparisons"])
    written = {}
    for relative, text in files.items():
        path = out_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        written[relative] = str(path)
    return written
