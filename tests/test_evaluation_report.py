"""Evaluation report: denominators, paired tests, consistency checks and figures."""

import csv
import importlib.util
import io
import json
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import pytest

from refactor_ai.evaluation import report
from refactor_ai.evaluation.protocol import arm_settings
from refactor_ai.evaluation.records import EvaluationRecord


def make(case: str, arm: str, *, ready: bool, failure: str = "none", latency: float = 1.0, **extra):
    failed = failure != "none"
    fields = {
        "evaluation_id": "eval-x",
        "protocol_version": "eval-v1",
        "protocol_status": "draft",
        "arm": arm,
        "case_id": case,
        "split": "validation",
        "source": extra.pop("source", "team-template"),
        "source_group": "tpl-x",
        "dataset_sha256": "d" * 64,
        "split_sha256": "s" * 64,
        "code_sha": None,
        "started_at": "2026-10-20T00:00:00+00:00",
        "provider_mode": "local_model",
        "model": None,
        "settings": arm_settings(arm).model_dump(mode="json"),
        "generation_seed": 42,
        "input_sha256": "i" * 64,
        "output_sha256": None if failed else "o" * 64,
        "proposed_code": None if failed else "def f():\n    return 1\n",
        "explanation": None,
        "run_status": "failed" if failed else "completed",
        "disposition": "failed" if failed else ("proposal_ready" if ready else "rejected"),
        "stop_reason": None,
        "error": None,
        "failure_type": failure,
        "syntax": "not_run" if failed else "pass",
        "rubric": "not_run" if failed else ("pass" if ready else "fail"),
        "reference_tests": (
            {"status": "not_run"}
            if failed
            else {"status": "pass", "total": 2, "passed": 2, "failed": 0, "errored": 0}
            if ready
            else {"status": "fail", "total": 2, "passed": 1, "failed": 1, "errored": 0}
        ),
        "model_review": "not_run",
        "recheck": {"syntax": "no_output", "rubric": "no_output"},
        "proposal_ready": ready and not failed,
        "attempt_count": 1,
        "reported_call_count": 1,
        "call_count": 0 if failed else 1,
        "prompt_tokens": None,
        "completion_tokens": None,
        "latency_s": latency,
        "worker_peak_rss_mb": None,
        "gpu_memory_used_mb": None,
        "evaluator": "test",
    }
    fields.update(extra)
    return json.loads(EvaluationRecord(**fields).model_dump_json())


def rows():
    out = []
    # 10 cases; A accepts 3, C accepts 8 (C-only 5 cases, both 3), one A timeout.
    for i in range(10):
        case = f"c{i:02d}"
        out.append(
            make(
                case,
                "A",
                ready=i < 3,
                failure="provider_timeout" if i == 9 else "none",
                latency=1.0 + i,
            )
        )
        out.append(
            make(case, "C", ready=i < 8, latency=2.0, source="mbpp" if i == 0 else "team-template")
        )
    return out


def test_denominators_include_failures():
    metrics = report.arm_metrics(rows())
    a = metrics["A"]
    assert a["attempted"] == 10
    assert a["rates"]["proposal_ready"] == {"numerator": 3, "denominator": 10, "rate": 0.3}
    assert a["rates"]["failed"]["numerator"] == 1 and a["rates"]["timeouts"]["numerator"] == 1
    assert a["rates"]["syntax_valid"]["numerator"] == 9  # the timeout has no proposal
    assert a["tests_pass_of_executed"] == {"numerator": 3, "denominator": 9, "rate": 3 / 9}
    assert a["latency_s"]["median"] == 5.0 and a["latency_s"]["p90"] == 9.0
    assert a["tokens"]["records_with_counts"] == 0 and a["tokens"]["mean"] is None
    assert metrics["C"]["rates"]["proposal_ready"]["numerator"] == 8


def test_exact_mcnemar_and_holm():
    assert report.exact_mcnemar(0, 0) == 1.0
    assert report.exact_mcnemar(5, 0) == pytest.approx(0.0625)
    assert report.exact_mcnemar(0, 5) == pytest.approx(0.0625)
    assert report.exact_mcnemar(9, 1) == pytest.approx(22 / 1024)
    assert report.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    paired = report.paired_comparisons(rows())
    assert [p["comparison"] for p in paired] == ["C vs A"]
    item = paired[0]
    assert (item["paired_cases"], item["both"], item["C_only"], item["A_only"]) == (10, 3, 5, 0)
    assert item["exact_mcnemar_p"] == pytest.approx(0.0625)


def test_consistency_checks():
    data = rows()
    report.check_consistency(data)
    with pytest.raises(report.ReportError, match="duplicate"):
        report.check_consistency(data + [data[0]])
    mixed = [dict(data[0], protocol_version="eval-v2")] + data[1:]
    with pytest.raises(report.ReportError, match="protocol_version"):
        report.check_consistency(mixed)
    with pytest.raises(report.ReportError, match="no evaluation records"):
        report.check_consistency([])


def test_build_report_writes_tables_and_valid_svg(tmp_path):
    written = report.build_report(rows(), tmp_path)
    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "| Overall acceptance (proposal_ready) | 3/10 (30.0%) | 8/10 (80.0%) |" in summary
    assert "| Timed out (provider or run) | 1/10 (10.0%) | 0/10 (0.0%) |" in summary
    assert "FAKE PROVIDER" not in summary
    table = list(csv.DictReader(io.StringIO((tmp_path / "arm_metrics.csv").read_text())))
    ready = [r for r in table if r["metric"] == "proposal_ready"]
    assert [(r["arm"], r["numerator"], r["denominator"]) for r in ready] == [
        ("A", "3", "10"),
        ("C", "8", "10"),
    ]
    for name in ("figures/outcome_rates.svg", "figures/latency.svg"):
        # Well-formedness check of the report's own generated SVG (no untrusted XML).
        root = ElementTree.fromstring((tmp_path / name).read_text(encoding="utf-8"))
        assert root.tag.endswith("svg")
    assert "3/10 (30.0%)" in (tmp_path / "figures/outcome_rates.svg").read_text(encoding="utf-8")
    assert set(written) >= {
        "summary.md",
        "paired.csv",
        "by_source.csv",
        "by_source_group.csv",
        "report.json",
    }
    again = tmp_path / "again"
    report.build_report(rows(), again)
    for name in written:
        assert (again / name).read_bytes() == (tmp_path / name).read_bytes()


def test_fake_provider_reports_are_labelled(tmp_path):
    data = [dict(row, provider_mode="fake") for row in rows()]
    report.build_report(data, tmp_path)
    assert "FAKE PROVIDER" in (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "Fake provider" in (tmp_path / "figures/outcome_rates.svg").read_text(encoding="utf-8")


def test_checks_of_a_failed_run_never_count_as_successes():
    # A record written before the harness fix: the review timed out after the workflow
    # had checked its last proposal, and those checks were copied into the outcome.
    stale = make(
        "c00",
        "B",
        ready=False,
        failure="provider_timeout",
        syntax="pass",
        rubric="pass",
        reference_tests={"status": "pass", "total": 2, "passed": 2, "failed": 0, "errored": 0},
    )
    rates = report.arm_metrics([stale])["B"]["rates"]
    for name in ("syntax_valid", "rubric_pass", "tests_pass", "tests_executed"):
        assert rates[name]["numerator"] == 0, name
    assert rates["failed"]["numerator"] == 1 and rates["timeouts"]["numerator"] == 1


def test_runner_errors_without_test_results_are_not_executed():
    data = [make(f"c{i:02d}", "C", ready=True) for i in range(8)]
    no_start = {"status": "error", "total": 2, "reason": "could not be started"}
    crashed = {"status": "error", "reason": "The reference runner failed unexpectedly"}
    crashed_mid = {"status": "error", "total": 2, "passed": 1, "failed": 0, "errored": 1}
    empty_pass = {"status": "pass", "total": 0, "passed": 0, "failed": 0, "errored": 0}
    for i, tests in enumerate((no_start, crashed, crashed_mid, empty_pass), start=8):
        data.append(make(f"c{i:02d}", "C", ready=False, reference_tests=tests))
    entry = report.arm_metrics(data)["C"]
    assert entry["rates"]["tests_executed"]["numerator"] == 9  # 8 passes and crashed_mid
    assert entry["rates"]["tests_pass"]["numerator"] == 8  # a pass with no test is no pass
    assert entry["tests_pass_of_executed"] == {"numerator": 8, "denominator": 9, "rate": 8 / 9}


def write_lines(path: Path, items: list[dict], tail: bytes = b"") -> None:
    text = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items)
    path.write_bytes(text.encode("utf-8") + tail)


def test_records_with_raw_unicode_line_separators_load(tmp_path):
    data = rows()[:2]
    data[0]["explanation"] = "guard\u2028clauses\u2029done\u0085."
    path = tmp_path / "records.jsonl"
    write_lines(path, data)
    assert "\u2028".encode() in path.read_bytes()
    assert report.load_records([path]) == data


def load_report_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "report_evaluation.py"
    spec = importlib.util.spec_from_file_location("report_evaluation_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_an_interrupted_last_line_is_named_not_a_traceback(tmp_path, capsys):
    data = rows()[:2]
    path = tmp_path / "records.jsonl"
    complete = (json.dumps(data[0]) + "\n").encode("utf-8")
    write_lines(path, data[:1], tail=json.dumps(data[1]).encode("utf-8")[:300])
    with pytest.raises(report.ReportError, match=rf"line 2 \(byte offset {len(complete)}\)"):
        report.load_records([path])
    script = load_report_script()
    assert script.main([str(path), "--out", str(tmp_path / "out")]) == 2
    error = capsys.readouterr().err
    assert "Cannot build the report" in error and "no line ending" in error
    assert not (tmp_path / "out").exists()
