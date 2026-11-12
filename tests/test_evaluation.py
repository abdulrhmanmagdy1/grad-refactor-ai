"""Unit tests for Evaluation Harness and Benchmark comparisons (FR09, UC04)."""

import json

import pytest

from core.exceptions import ExecutionTimeoutError
from evaluation.harness import (
    DEFAULT_BENCHMARK_CASES,
    EvaluationHarness,
    load_dataset_cases,
)


@pytest.mark.anyio
async def test_evaluation_harness_execution(tmp_path):
    # Run evaluation on subset of benchmark cases
    cases = DEFAULT_BENCHMARK_CASES[:2]
    harness = EvaluationHarness(cases=cases)

    records, summary = await harness.run_all(groups=["A", "B"])

    assert len(records) == 4  # 2 cases * 2 groups
    assert "Group-A-Baseline" in summary["groups"]
    assert "Group-B-MultiAgent" in summary["groups"]

    grp_b = summary["groups"]["Group-B-MultiAgent"]
    assert grp_b["syntax_validity_rate"] == 1.0
    assert grp_b["overall_acceptance_rate"] == 1.0
    assert grp_b["mean_latency_ms"] > 0
    assert grp_b["mean_total_tokens"] > 0

    # Test export to CSV and JSON
    csv_file, json_file = harness.export_results(records, summary, output_dir=tmp_path)
    assert csv_file.exists()
    assert json_file.exists()
    assert csv_file.stat().st_size > 0

    summary_loaded = json.loads(json_file.read_text(encoding="utf-8"))
    assert summary_loaded["total_evaluations"] == 4


def test_harness_caches_baseline_provider():
    harness = EvaluationHarness(cases=DEFAULT_BENCHMARK_CASES[:1])

    assert harness._baseline_provider() is harness._baseline_provider()


@pytest.mark.anyio
async def test_run_all_releases_baseline_before_loading_adapter(monkeypatch):
    harness = EvaluationHarness(cases=DEFAULT_BENCHMARK_CASES[:1])
    events: list[str] = []
    harness._baseline_provider_instance = object()

    async def fake_baseline(case):
        events.append("baseline")
        return {"group": "Group-A-Baseline"}

    async def fake_adapter(case):
        events.append("adapter")
        assert harness._baseline_provider_instance is None
        harness._adapter_provider_instance = object()
        return {"group": "Group-C-FineTunedSingle"}

    monkeypatch.setattr(harness, "run_group_a_baseline", fake_baseline)
    monkeypatch.setattr(harness, "run_group_c_finetuned_single", fake_adapter)
    monkeypatch.setattr(harness, "_compute_summary", lambda records: {})

    records, _ = await harness.run_all(groups=["A", "C"])

    assert [record["group"] for record in records] == [
        "Group-A-Baseline",
        "Group-C-FineTunedSingle",
    ]
    assert events == ["baseline", "adapter"]


@pytest.mark.anyio
async def test_run_all_limit_keeps_a_pilot_subset(monkeypatch):
    harness = EvaluationHarness(cases=DEFAULT_BENCHMARK_CASES[:3])
    seen: list[str] = []

    async def fake_baseline(case):
        seen.append(case.case_id)
        return {"group": "Group-A-Baseline"}

    monkeypatch.setattr(harness, "run_group_a_baseline", fake_baseline)
    monkeypatch.setattr(harness, "_compute_summary", lambda records: {})

    records, _ = await harness.run_all(groups=["A"], limit=2)

    assert seen == [case.case_id for case in DEFAULT_BENCHMARK_CASES[:2]]
    assert len(records) == 2


@pytest.mark.anyio
async def test_generation_timeout_is_counted_as_executed_failure(monkeypatch):
    class TimeoutProvider:
        async def generate_refactoring(self, code, findings, options=None):
            raise ExecutionTimeoutError("generation exceeded the bound")

    harness = EvaluationHarness(cases=DEFAULT_BENCHMARK_CASES[:1])
    monkeypatch.setattr(harness, "_baseline_provider", lambda: TimeoutProvider())

    record = await harness.run_group_a_baseline(harness.cases[0])

    assert record["status"] == "executed"
    assert record["failure_type"] == "generation_timeout"
    assert record["refactor_success"] is False


def test_dataset_loader_only_targets_explicit_smell_rules(tmp_path):
    rows = [
        {
            "id": "smelly",
            "source_group": "repo-a",
            "split": "test",
            "prompt": "def f(x):\n    return x\n",
            "completion": "def f(x):\n    return x\n",
            "license": "CC0-1.0",
            "refactoring_type": "long-function",
            "smell_rule": "long-function",
        },
        {
            "id": "clean",
            "source_group": "repo-b",
            "split": "test",
            "prompt": "def g(x):\n    return x\n",
            "completion": "def g(x):\n    return x\n",
            "license": "CC0-1.0",
            "refactoring_type": "long-function",
            "smell_rule": None,
        },
    ]
    path = tmp_path / "tiny.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    cases = load_dataset_cases(path, "test")

    assert cases[0].expected_rule == "long-function"
    assert cases[1].expected_rule is None


def test_export_results_writes_lf_line_endings(tmp_path):
    harness = EvaluationHarness(cases=DEFAULT_BENCHMARK_CASES[:1])
    records = [{"case_id": "c1", "group": "Group-A-Baseline", "status": "executed"}]
    summary = {"total_evaluations": 1, "groups": {}}

    csv_file, json_file = harness.export_results(records, summary, output_dir=tmp_path, name="lf")

    assert b"\r\n" not in csv_file.read_bytes()
    assert b"\r\n" not in json_file.read_bytes()
