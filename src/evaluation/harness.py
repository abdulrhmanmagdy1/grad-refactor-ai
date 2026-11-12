"""Evaluation Benchmark Harness (FR09, ADR08, UC04, Phase 5).

Implements systematic comparison across:

- Group A: Baseline Single-Prompt (direct refactoring without multi-agent coordination)
- Group B: Multi-Agent Coordination (Analysis + Refactoring + Review)
- Group C: Fine-Tuned Model (Single-Role)
- Group D: Fine-Tuned Modification Role + Multi-Agent Coordination

Measured metrics per case:

- syntax validity, sandbox test outcome, review verdict, acceptance
- worst-case latency and real token counters per provider
- CodeBLEU (Python variant) and AST similarity against the original module
- Maintainability Index improvement and cyclomatic-complexity reduction
- execution pass@1 on the first candidate attempt
- ``smell_rule_resolved``: the declared finding disappeared from the candidate
- ``refactor_success``: syntax valid + symbols preserved + tests available and
  passing + the declared finding was not left unresolved. Clean-control rows
  have no declared finding, so success means "left the clean module alone and
  kept its behaviour".

Honesty policy (NFR06): when no trained LoRA adapter exists on this machine,
Groups C and D emit explicit ``provider_unavailable`` rows instead of
pretending a base model or fallback was fine-tuned. Rates over zero executed
cases are ``null``, never a fabricated 0 or 1.

Exports case-level records to CSV and the aggregate summary to JSON. With
``--include-code`` the CSV also carries the original and refactored source of
every executed row — the required input for the blind human-review workflow
(``scripts/prepare_blind_review.py``).
"""

import argparse
import asyncio
import csv
import gc
import json
import statistics
import time
from pathlib import Path
from typing import Any

from agents.analysis_agent import AnalysisAgent
from agents.refactoring_agent import RefactoringAgent
from agents.review_agent import ReviewAgent
from core.exceptions import ExecutionTimeoutError, ProviderUnavailableError
from evaluation.metrics import ast_similarity_score, codebleu_score
from models.local_provider import (
    DEFAULT_BASE_MODEL,
    LocalModelProvider,
    resolve_adapter_base_model,
)
from models.mock_provider import MockModelProvider
from runner.sandbox import IsolatedRunner

# Default location produced by training/train_lora.py per configs/training.example.json.
DEFAULT_ADAPTER_PATH = Path("runs/lora-first/adapter")


class BenchmarkCase:
    """A test case in the benchmark harness."""

    def __init__(
        self,
        case_id: str,
        source_group: str,
        original_code: str,
        test_code: str | None = None,
        refactoring_type: str = "general",
        expected_rule: str | None = None,
        variant: str = "findings",
    ) -> None:
        self.case_id = case_id
        self.source_group = source_group
        self.original_code = original_code
        self.test_code = test_code
        self.refactoring_type = refactoring_type
        self.expected_rule = expected_rule
        self.variant = variant


def load_dataset_cases(dataset_path: Path | str, split: str = "test") -> list["BenchmarkCase"]:
    """Load curated-dataset records for one split as benchmark cases.

    Test code is intentionally omitted: the Review Agent auto-synthesizes
    golden-baseline equivalence tests against the original module instead.
    """
    path = Path(dataset_path)
    cases: list[BenchmarkCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("split") != split:
            continue
        cases.append(
            BenchmarkCase(
                case_id=str(row["id"]),
                source_group=str(row["source_group"]),
                original_code=str(row["prompt"]),
                test_code=None,
                refactoring_type=str(row.get("refactoring_type") or "general"),
                # Only an explicit smell_rule creates a resolution target. Clean
                # controls have `smell_rule: null`; falling back to
                # refactoring_type would incorrectly demand a refactor there.
                expected_rule=str(row["smell_rule"]) if row.get("smell_rule") else None,
                variant=str(row.get("variant") or "findings"),
            )
        )
    if not cases:
        raise ValueError(f"No records with split '{split}' found in {path}")
    return cases


# Built-in benchmark suite covering the supported refactoring targets
DEFAULT_BENCHMARK_CASES: list[BenchmarkCase] = [
    BenchmarkCase(
        case_id="case-01-long-fn",
        source_group="repo-core",
        refactoring_type="long-function",
        expected_rule="long-function",
        original_code="def process_batch(items):\n"
        + "\n".join([f"    x_{i} = {i}" for i in range(35)])
        + "\n    return items\n",
        test_code=(
            "from solution import process_batch\n"
            "def test_process():\n"
            "    assert process_batch([1, 2]) == [1, 2]\n"
        ),
    ),
    BenchmarkCase(
        case_id="case-02-deep-nesting",
        source_group="repo-utils",
        refactoring_type="deep-nesting",
        expected_rule="deep-nesting",
        original_code=(
            "def check_permissions(user, resource, action, env):\n"
            "    if user:\n"
            "        if resource:\n"
            "            if action:\n"
            "                if env == 'prod':\n"
            "                    return True\n"
            "    return False\n"
        ),
        test_code=(
            "from solution import check_permissions\n"
            "def test_perms():\n"
            "    assert check_permissions(True, True, True, 'prod') is True\n"
            "    assert check_permissions(False, True, True, 'prod') is False\n"
        ),
    ),
    BenchmarkCase(
        case_id="case-03-async-stream",
        source_group="repo-async",
        refactoring_type="async-function",
        expected_rule="long-function",
        original_code=(
            "async def handle_stream(data):\n"
            + "\n".join([f"    step_{i} = await fetch({i})" for i in range(32)])
            + "\n    return len(data)\n"
        ),
        test_code=None,
    ),
    BenchmarkCase(
        case_id="case-04-high-complexity",
        source_group="repo-calc",
        refactoring_type="high-complexity",
        expected_rule="high-complexity",
        original_code=(
            "def route_event(event_type, payload):\n"
            "    if event_type == 'a':\n"
            "        return 1\n"
            "    elif event_type == 'b':\n"
            "        return 2\n"
            "    elif event_type == 'c':\n"
            "        return 3\n"
            "    elif event_type == 'd':\n"
            "        return 4\n"
            "    elif event_type == 'e':\n"
            "        return 5\n"
            "    elif event_type == 'f':\n"
            "        return 6\n"
            "    return 0\n"
        ),
        test_code=(
            "from solution import route_event\n"
            "def test_routing():\n"
            "    assert route_event('a', {}) == 1\n"
            "    assert route_event('z', {}) == 0\n"
        ),
    ),
]


class EvaluationHarness:
    """Benchmark runner executing comparative experiments (FR09)."""

    def __init__(
        self,
        cases: list[BenchmarkCase] | None = None,
        runner: IsolatedRunner | None = None,
        adapter_path: Path | str = DEFAULT_ADAPTER_PATH,
        include_code: bool = False,
        base_model_name: str | None = None,
        baseline: str = "mock",
        num_candidates: int = 1,
        load_in_4bit: bool = False,
        timeout_seconds: float = 900.0,
    ) -> None:
        self.cases = cases or DEFAULT_BENCHMARK_CASES
        self.runner = runner or IsolatedRunner()
        self.adapter_path = str(adapter_path)
        self.include_code = include_code
        self.base_model_name = base_model_name
        self.baseline = baseline
        self.num_candidates = max(1, int(num_candidates))
        self.load_in_4bit = load_in_4bit
        # Local HF generation is much slower than a mock provider. A single
        # `generate_refactoring` call may cover best-of-N completions, so the
        # timeout must bound the whole call, not one token stream (FR08).
        self.timeout_seconds = float(timeout_seconds)
        # Loading a multi-gigabyte checkpoint per case would dominate runtime
        # and thrash GPU memory; keep one provider (and one loaded model) per
        # baseline/adapter for the whole benchmark.
        self._baseline_provider_instance = None
        self._adapter_provider_instance = None

    def _resolved_base_model(self) -> str:
        """Use the adapter's recorded base, an explicit value, or the default."""
        return (
            self.base_model_name
            or resolve_adapter_base_model(self.adapter_path)
            or DEFAULT_BASE_MODEL
        )

    def _baseline_provider(self):
        if self._baseline_provider_instance is not None:
            return self._baseline_provider_instance
        if self.baseline == "mock":
            self._baseline_provider_instance = MockModelProvider()
        else:
            self._baseline_provider_instance = LocalModelProvider(
                model_name=self._resolved_base_model(),
                base_model_name=self._resolved_base_model(),
                require_hf=True,
                num_candidates=self.num_candidates,
                load_in_4bit=self.load_in_4bit,
                timeout_seconds=self.timeout_seconds,
            )
        return self._baseline_provider_instance

    def _adapter_provider(self) -> LocalModelProvider:
        if self._adapter_provider_instance is None:
            self._adapter_provider_instance = LocalModelProvider(
                model_name=self._resolved_base_model(),
                base_model_name=self._resolved_base_model(),
                adapter_path=self.adapter_path,
                num_candidates=self.num_candidates,
                load_in_4bit=self.load_in_4bit,
                timeout_seconds=self.timeout_seconds,
            )
        return self._adapter_provider_instance

    def _release_baseline_provider(self) -> None:
        """Drop the cached base model before the adapter is loaded.

        A 3B fp16 base model and a second 3B fp16 model with its PEFT adapter
        do not fit together on a 15 GB T4. The harness runs groups A/B first,
        then releases this instance so groups C/D can load the adapter without
        resorting to CPU offload or a quantized model that was never trained.
        """
        if self._baseline_provider_instance is None:
            return
        self._baseline_provider_instance = None
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001 - optional dependency
            pass

    # ------------------------------------------------------------------ #
    # Group runners
    # ------------------------------------------------------------------ #
    async def run_group_a_baseline(self, case: BenchmarkCase) -> dict[str, Any]:
        """Group A: Baseline Single-Prompt (direct generation, no coordination)."""
        try:
            provider = self._baseline_provider()
            t0 = time.perf_counter()

            # Give the single-prompt baseline the same findings the multi-agent
            # pipeline receives; otherwise it is not a fair comparison and its
            # acceptance rate measures doing nothing (NFR06).
            analysis = await AnalysisAgent().analyze(case.original_code)
            refactored, meta = await provider.generate_refactoring(
                case.original_code, analysis.findings
            )
            duration_ms = (time.perf_counter() - t0) * 1000

            review_agent = ReviewAgent(self.runner)
            verif, _diff, _auto_tests = review_agent.review(
                case.original_code, refactored, case.test_code
            )
            pass_at_1 = verif.tests_passed if verif.tests_available else None
            return self._build_case_record(
                case, "Group-A-Baseline", refactored, meta, verif, duration_ms, 0, pass_at_1
            )
        except ProviderUnavailableError as exc:
            return self._provider_failure_record(case, "Group-A-Baseline", exc)
        except ExecutionTimeoutError as exc:
            return self._generation_timeout_record(case, "Group-A-Baseline", exc)

    async def run_group_b_multiagent(self, case: BenchmarkCase) -> dict[str, Any]:
        """Group B: Multi-Agent Coordination (Analysis -> Refactoring -> Review)."""
        try:
            provider = self._baseline_provider()
            analysis_agent = AnalysisAgent()
            refactor_agent = RefactoringAgent(provider)
            review_agent = ReviewAgent(self.runner)

            t0 = time.perf_counter()
            analysis = await analysis_agent.analyze(case.original_code)

            refactored, meta = await refactor_agent.refactor(case.original_code, analysis.findings)
            verif, _diff, _auto_tests = review_agent.review(
                case.original_code, refactored, case.test_code
            )
            pass_at_1 = verif.tests_passed if verif.tests_available else None
            retries = 0

            # Bounded retry loop (max 1 retry), mirroring the orchestrator: only a
            # *rejected* candidate is regenerated; "uncertain" completes with a flag.
            if verif.review_verdict == "rejected":
                retries = 1
                retry_feedback = (
                    f"Failed review: {verif.review_notes}. Fix syntax and keep symbols."
                )
                refactored, meta = await refactor_agent.refactor(
                    case.original_code, analysis.findings, retry_feedback=retry_feedback
                )
                verif, _diff, _auto_tests = review_agent.review(
                    case.original_code, refactored, case.test_code
                )

            duration_ms = (time.perf_counter() - t0) * 1000
            return self._build_case_record(
                case,
                "Group-B-MultiAgent",
                refactored,
                meta,
                verif,
                duration_ms,
                retries,
                pass_at_1,
            )
        except ProviderUnavailableError as exc:
            return self._provider_failure_record(case, "Group-B-MultiAgent", exc)
        except ExecutionTimeoutError as exc:
            return self._generation_timeout_record(case, "Group-B-MultiAgent", exc)

    async def run_group_c_finetuned_single(self, case: BenchmarkCase) -> dict[str, Any]:
        """Group C: Fine-Tuned Model (Single role)."""
        try:
            provider = self._adapter_provider()
            t0 = time.perf_counter()
            refactored, meta = await provider.generate_refactoring(case.original_code, [])
            duration_ms = (time.perf_counter() - t0) * 1000

            review_agent = ReviewAgent(self.runner)
            verif, _diff, _auto_tests = review_agent.review(
                case.original_code, refactored, case.test_code
            )
            pass_at_1 = verif.tests_passed if verif.tests_available else None
            return self._build_case_record(
                case, "Group-C-FineTunedSingle", refactored, meta, verif, duration_ms, 0, pass_at_1
            )
        except ProviderUnavailableError as exc:
            return self._provider_failure_record(case, "Group-C-FineTunedSingle", exc)
        except ExecutionTimeoutError as exc:
            return self._generation_timeout_record(case, "Group-C-FineTunedSingle", exc)

    async def run_group_d_finetuned_multiagent(self, case: BenchmarkCase) -> dict[str, Any]:
        """Group D: Fine-Tuned Model in modification role + multi-agent coordination."""
        try:
            provider = self._adapter_provider()
            analysis_agent = AnalysisAgent()
            refactor_agent = RefactoringAgent(provider)
            review_agent = ReviewAgent(self.runner)

            t0 = time.perf_counter()
            analysis = await analysis_agent.analyze(case.original_code)

            refactored, meta = await refactor_agent.refactor(case.original_code, analysis.findings)
            verif, _diff, _auto_tests = review_agent.review(
                case.original_code, refactored, case.test_code
            )
            pass_at_1 = verif.tests_passed if verif.tests_available else None
            retries = 0

            if verif.review_verdict == "rejected":
                retries = 1
                retry_feedback = (
                    f"Failed review: {verif.review_notes}. Fix syntax and keep symbols."
                )
                refactored, meta = await refactor_agent.refactor(
                    case.original_code, analysis.findings, retry_feedback=retry_feedback
                )
                verif, _diff, _auto_tests = review_agent.review(
                    case.original_code, refactored, case.test_code
                )

            duration_ms = (time.perf_counter() - t0) * 1000
            return self._build_case_record(
                case,
                "Group-D-FineTunedMultiAgent",
                refactored,
                meta,
                verif,
                duration_ms,
                retries,
                pass_at_1,
            )
        except ProviderUnavailableError as exc:
            return self._provider_failure_record(case, "Group-D-FineTunedMultiAgent", exc)
        except ExecutionTimeoutError as exc:
            return self._generation_timeout_record(case, "Group-D-FineTunedMultiAgent", exc)

    # ------------------------------------------------------------------ #
    # Record building
    # ------------------------------------------------------------------ #
    def _build_case_record(
        self,
        case: BenchmarkCase,
        group_name: str,
        refactored_code: str,
        meta: dict[str, Any],
        verif: Any,
        duration_ms: float,
        retries_used: int,
        pass_at_1: bool | None,
    ) -> dict[str, Any]:
        orig_lines = len(case.original_code.splitlines())
        refact_lines = len(refactored_code.splitlines())

        metrics_before = getattr(verif, "metrics_before", {}) or {}
        metrics_after = getattr(verif, "metrics_after", {}) or {}
        mi_before = metrics_before.get("maintainability_index")
        mi_after = metrics_after.get("maintainability_index")
        complexity_before = metrics_before.get("total_cyclomatic_complexity")
        complexity_after = metrics_after.get("total_cyclomatic_complexity")
        complexity_reduction_pct: float | None = None
        if complexity_before:
            complexity_reduction_pct = round(
                (complexity_before - (complexity_after or 0)) / complexity_before * 100, 2
            )

        resolved_rules = set(verif.details.get("resolved_findings", []) or [])
        smell_rule_resolved = case.expected_rule in resolved_rules if case.expected_rule else None
        preserved_symbols = bool(getattr(verif, "preserved_symbols", False))
        refactor_success = bool(
            verif.syntax_valid
            and preserved_symbols
            and verif.tests_available
            and verif.tests_passed
            and smell_rule_resolved is not False
        )

        record = {
            "case_id": case.case_id,
            "source_group": case.source_group,
            "group": group_name,
            "refactoring_type": case.refactoring_type,
            "variant": case.variant,
            "expected_rule": case.expected_rule,
            "status": "executed",
            "failure_type": None,
            "error": "",
            "syntax_valid": verif.syntax_valid,
            "preserved_symbols": preserved_symbols,
            "smell_rule_resolved": smell_rule_resolved,
            "refactor_success": refactor_success,
            "tests_available": verif.tests_available,
            "tests_passed": verif.tests_passed,
            "execution_pass_at_1": pass_at_1,
            "review_verdict": verif.review_verdict,
            "is_accepted": verif.review_verdict == "approved",
            "duration_ms": round(duration_ms, 2),
            "retries_used": retries_used,
            "prompt_tokens": meta.get("prompt_tokens", 0),
            "completion_tokens": meta.get("completion_tokens", 0),
            "total_tokens": meta.get("total_tokens", 0)
            or (meta.get("prompt_tokens", 0) + meta.get("completion_tokens", 0)),
            "loc_before": orig_lines,
            "loc_after": refact_lines,
            "loc_delta": refact_lines - orig_lines,
            "codebleu_score": codebleu_score(case.original_code, refactored_code),
            "ast_similarity_score": ast_similarity_score(case.original_code, refactored_code),
            "mi_before": mi_before,
            "mi_after": mi_after,
            "mi_delta": (
                round(float(mi_after) - float(mi_before), 4)
                if mi_before is not None and mi_after is not None
                else None
            ),
            "complexity_before": complexity_before,
            "complexity_after": complexity_after,
            "complexity_reduction_pct": complexity_reduction_pct,
            "model": meta.get("model", "unknown"),
            "candidates_generated": meta.get("candidates_generated", 1),
            "selected_candidate": meta.get("selected_candidate", 0),
        }
        if self.include_code:
            record["original_code"] = case.original_code
            record["refactored_code"] = refactored_code
        return record

    def _provider_failure_record(
        self, case: BenchmarkCase, group_name: str, exc: Exception
    ) -> dict[str, Any]:
        """Honest row for a group whose real model/adapter cannot run here (NFR06)."""
        return {
            "case_id": case.case_id,
            "source_group": case.source_group,
            "group": group_name,
            "refactoring_type": case.refactoring_type,
            "variant": case.variant,
            "expected_rule": case.expected_rule,
            "status": "provider_unavailable",
            "failure_type": "provider_unavailable",
            "error": str(exc),
            "syntax_valid": False,
            "preserved_symbols": False,
            "smell_rule_resolved": None,
            "refactor_success": False,
            "tests_available": False,
            "tests_passed": False,
            "execution_pass_at_1": None,
            "review_verdict": "not_reviewed",
            "is_accepted": False,
            "duration_ms": 0.0,
            "retries_used": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "loc_before": len(case.original_code.splitlines()),
            "loc_after": 0,
            "loc_delta": 0,
            "codebleu_score": None,
            "ast_similarity_score": None,
            "mi_before": None,
            "mi_after": None,
            "mi_delta": None,
            "complexity_before": None,
            "complexity_after": None,
            "complexity_reduction_pct": None,
            "model": "unavailable",
            "candidates_generated": 0,
            "selected_candidate": -1,
        }

    def _generation_timeout_record(
        self, case: BenchmarkCase, group_name: str, exc: Exception
    ) -> dict[str, Any]:
        """Executed-but-failed row when generation exceeds the declared bound.

        Unlike ``provider_unavailable``, the model *was* usable here, so the
        case stays in the denominator as a failure instead of disappearing
        from the success rate (NFR06).
        """
        record = self._provider_failure_record(case, group_name, exc)
        record.update(
            {
                "status": "executed",
                "failure_type": "generation_timeout",
                "error": str(exc),
                "model": "timeout",
            }
        )
        return record

    # ------------------------------------------------------------------ #
    # Aggregation + export
    # ------------------------------------------------------------------ #
    async def run_all(
        self, groups: list[str] | None = None, limit: int | None = None
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Run all test cases across selected groups and compute summary statistics.

        ``limit`` keeps the first N cases of the split. It exists so a short
        pilot can prove the model, adapter and sandbox work before paying for
        a multi-hour full evaluation.
        """
        groups = groups or ["A", "B", "C", "D"]
        cases = self.cases if limit is None else self.cases[: max(0, int(limit))]
        if not cases:
            raise ValueError("run_all needs at least one case; limit removed every case")
        records: list[dict[str, Any]] = []
        baseline_groups = [group for group in ("A", "B") if group in groups]
        adapter_groups = [group for group in ("C", "D") if group in groups]

        # Run all baseline cases first. The base model is released before the
        # first adapter call so a 3B base and a 3B adapter never share the T4.
        if baseline_groups:
            for index, case in enumerate(cases, 1):
                print(
                    f"[eval] baseline case {index}/{len(cases)}: {case.case_id}",
                    flush=True,
                )
                if "A" in baseline_groups:
                    records.append(await self.run_group_a_baseline(case))
                if "B" in baseline_groups:
                    records.append(await self.run_group_b_multiagent(case))

        if baseline_groups and adapter_groups:
            self._release_baseline_provider()

        if adapter_groups:
            for index, case in enumerate(cases, 1):
                print(
                    f"[eval] adapter case {index}/{len(cases)}: {case.case_id}",
                    flush=True,
                )
                if "C" in adapter_groups:
                    records.append(await self.run_group_c_finetuned_single(case))
                if "D" in adapter_groups:
                    records.append(await self.run_group_d_finetuned_multiagent(case))

        summary = self._compute_summary(records)
        return records, summary

    @staticmethod
    def _mean(values: list[Any], digits: int = 4) -> float:
        numeric = [float(value) for value in values if value is not None]
        return round(statistics.mean(numeric), digits) if numeric else 0.0

    def _compute_summary(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Aggregate statistical metrics per group."""
        group_records: dict[str, list[dict[str, Any]]] = {}
        for r in records:
            group_records.setdefault(r["group"], []).append(r)

        summary_by_group: dict[str, Any] = {}
        for grp, recs in group_records.items():
            total = len(recs)
            executed = [r for r in recs if r["status"] == "executed"]
            syntax_valid_count = sum(1 for r in executed if r["syntax_valid"])
            testable_recs = [r for r in executed if r["tests_available"]]
            tests_passed_count = sum(1 for r in testable_recs if r["tests_passed"])
            accepted_count = sum(1 for r in executed if r["is_accepted"])
            success_count = sum(1 for r in executed if r["refactor_success"])
            findings_recs = [r for r in executed if r.get("variant") == "findings"]
            clean_recs = [r for r in executed if r.get("variant") == "clean-control"]
            findings_success = sum(1 for r in findings_recs if r["refactor_success"])
            clean_success = sum(1 for r in clean_recs if r["refactor_success"])
            smell_recs = [r for r in executed if r.get("smell_rule_resolved") is not None]
            smell_resolved_count = sum(1 for r in smell_recs if r["smell_rule_resolved"])
            latencies = [r["duration_ms"] for r in executed]
            tokens = [r["total_tokens"] for r in executed]
            pass_at_1_eligible = [r for r in executed if r["execution_pass_at_1"] is not None]
            pass_at_1_passed = sum(1 for r in pass_at_1_eligible if r["execution_pass_at_1"])

            # Rates over executed cases; `None` means "not measured", which is
            # how groups whose provider/adapter is unavailable must read
            # (NFR06) — never a fabricated 0/1.
            summary_by_group[grp] = {
                "total_cases": total,
                "executed_cases": len(executed),
                "provider_unavailable_cases": total - len(executed),
                "syntax_validity_rate": round(syntax_valid_count / len(executed), 4)
                if executed
                else None,
                "test_pass_rate": round(tests_passed_count / len(testable_recs), 4)
                if testable_recs
                else None,
                "smell_resolution_rate": round(smell_resolved_count / len(smell_recs), 4)
                if smell_recs
                else None,
                "refactor_success_rate": round(success_count / len(executed), 4)
                if executed
                else None,
                "findings_cases": len(findings_recs),
                "clean_control_cases": len(clean_recs),
                "findings_refactor_success_rate": round(findings_success / len(findings_recs), 4)
                if findings_recs
                else None,
                "clean_control_success_rate": round(clean_success / len(clean_recs), 4)
                if clean_recs
                else None,
                "overall_acceptance_rate": round(accepted_count / len(executed), 4)
                if executed
                else None,
                "mean_latency_ms": round(statistics.mean(latencies), 2) if latencies else None,
                "mean_total_tokens": round(statistics.mean(tokens), 1) if tokens else None,
                "total_retries": sum(r["retries_used"] for r in executed),
                # Phase 5 academic metrics
                "codebleu_score_mean": self._mean([r["codebleu_score"] for r in executed])
                if executed
                else None,
                "ast_similarity_mean": self._mean([r["ast_similarity_score"] for r in executed])
                if executed
                else None,
                "mi_improvement_mean": self._mean([r["mi_delta"] for r in executed], digits=2)
                if executed
                else None,
                "complexity_reduction_pct_mean": self._mean(
                    [r["complexity_reduction_pct"] for r in executed], digits=2
                )
                if executed
                else None,
                "execution_pass_at_1": round(pass_at_1_passed / len(pass_at_1_eligible), 4)
                if pass_at_1_eligible
                else None,
            }

        return {
            "total_evaluations": len(records),
            "config": {
                "baseline": self.baseline,
                "base_model": self._resolved_base_model(),
                "adapter_path": self.adapter_path,
                "num_candidates": self.num_candidates,
                "load_in_4bit": self.load_in_4bit,
                "timeout_seconds": self.timeout_seconds,
            },
            "groups": summary_by_group,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def export_results(
        self,
        records: list[dict[str, Any]],
        summary: dict[str, Any],
        output_dir: Path | str = Path("experiments"),
        name: str = "evaluation",
    ) -> tuple[Path, Path]:
        """Export case-level records to CSV and summary report to JSON."""
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        csv_file = out_path / f"{name}_results.csv"
        json_file = out_path / f"{name}_summary.json"

        # Union of keys, preserving first-seen order, so every record fits.
        fieldnames: list[str] = []
        for record in records:
            for key in record:
                if key not in fieldnames:
                    fieldnames.append(key)

        if records:
            with open(csv_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=fieldnames,
                    extrasaction="ignore",
                    restval="",
                    lineterminator="\n",
                )
                writer.writeheader()
                writer.writerows(records)

        with open(json_file, "w", encoding="utf-8", newline="\n") as f:
            json.dump(summary, f, indent=2)

        return csv_file, json_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Refactoring Evaluation Harness")
    parser.add_argument("--output-dir", type=str, default="experiments")
    parser.add_argument("--groups", nargs="+", default=["A", "B", "C", "D"])
    parser.add_argument(
        "--dataset",
        type=str,
        default=None,
        help="Optional curated JSONL dataset; runs its split instead of the built-in suite.",
    )
    parser.add_argument("--split", type=str, default="test")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only evaluate the first N cases of the split (pilot smoke run).",
    )
    parser.add_argument("--name", type=str, default="evaluation")
    parser.add_argument("--adapter-path", type=str, default=str(DEFAULT_ADAPTER_PATH))
    parser.add_argument(
        "--base-model",
        type=str,
        default=None,
        help=(
            "Base checkpoint used by groups A/B and as the adapter base. "
            "Defaults to the adapter_config.json base (or the 1.5B default)."
        ),
    )
    parser.add_argument(
        "--baseline",
        choices=("mock", "base"),
        default="mock",
        help=(
            "Provider for groups A/B. 'mock' keeps the deterministic CPU baseline; "
            "'base' compares against the real (untrained) base model."
        ),
    )
    parser.add_argument(
        "--candidates",
        type=int,
        default=1,
        help="Best-of-N candidates for local HF inference (AST-only selection).",
    )
    parser.add_argument(
        "--load-in-4bit",
        action="store_true",
        help="Load the base model in 4-bit NF4 (needs bitsandbytes + CUDA).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=900.0,
        help=(
            "Per-call generation timeout in seconds for local HF providers. "
            "Covers all best-of-N candidates in one call."
        ),
    )
    parser.add_argument(
        "--include-code",
        action="store_true",
        help=(
            "Also export the original and refactored code with executed rows; "
            "required as input for scripts/prepare_blind_review.py."
        ),
    )
    args = parser.parse_args()

    cases = load_dataset_cases(args.dataset, args.split) if args.dataset else None
    harness = EvaluationHarness(
        cases=cases,
        adapter_path=args.adapter_path,
        include_code=args.include_code,
        base_model_name=args.base_model,
        baseline=args.baseline,
        num_candidates=max(1, args.candidates),
        load_in_4bit=args.load_in_4bit,
        timeout_seconds=args.timeout,
    )
    records, summary = asyncio.run(harness.run_all(groups=args.groups, limit=args.limit))
    csv_path, json_path = harness.export_results(
        records, summary, output_dir=args.output_dir, name=args.name
    )
    print(f"Evaluation complete: {len(records)} case records exported.")
    print(f"CSV:  {csv_path}")
    print(f"JSON: {json_path}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
