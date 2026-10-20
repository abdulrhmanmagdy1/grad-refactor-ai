"""Curation-only executor: runs trusted functions in separate interpreter processes.

This is not the reference runner used by the service. It exists only to produce and
check reference tests while building the dataset, and it only ever receives trusted
code: the team's template functions, functions from licensed datasets that passed the
task's static checks (no imports, no I/O or dynamic-execution builtins), and their
reference transformations or mutants. It is never used for user input.

Isolation is limited to what a curation job needs: a separate ``python -S -P`` process
(no site-packages, no script directory on sys.path) with a minimal environment
(PYTHONHASHSEED fixed, no PYTHONPATH), a fresh temporary working directory that is
removed afterwards, a deterministic line-event budget per call and a wall-clock timeout
per batch. Batches that fail are retried job by job so one bad job cannot hide others.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

HARNESS_SOURCE = (Path(__file__).with_name("_harness.py")).read_text(encoding="utf-8")
DEFAULT_LINE_BUDGET = 200_000
DEFAULT_BATCH_TIMEOUT_S = 300.0
DEFAULT_JOB_TIMEOUT_S = 60.0
MODES = ("outcome", "lines", "branches")


@dataclass(frozen=True)
class Job:
    """One function and the calls to make. calls holds (args, kwargs) literal sources."""

    job_id: str
    code: str
    function: str
    calls: tuple[tuple[str, str], ...]
    mode: str = "outcome"

    def payload(self) -> dict:
        if self.mode not in MODES:
            raise ValueError(f"unknown mode {self.mode}")
        return {
            "id": self.job_id,
            "code": self.code,
            "function": self.function,
            "calls": [list(call) for call in self.calls],
            "mode": self.mode,
        }


@dataclass
class JobResult:
    job_id: str
    results: list[dict] = field(default_factory=list)
    error: str | None = None


def _environment(hash_seed: int) -> dict[str, str]:
    env = {
        "PYTHONHASHSEED": str(hash_seed),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if os.name == "nt" and os.environ.get("SYSTEMROOT"):
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]  # required to start Python on Windows
    return env


def _run_batch(
    jobs: list[Job], hash_seed: int, line_budget: int, timeout_s: float
) -> list[JobResult]:
    payload = json.dumps({"line_budget": line_budget, "jobs": [job.payload() for job in jobs]})
    with tempfile.TemporaryDirectory(prefix="curation-exec-") as workdir:
        completed = subprocess.run(
            [sys.executable, "-S", "-P", "-X", "utf8", "-c", HARNESS_SOURCE],
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout_s,
            cwd=workdir,
            env=_environment(hash_seed),
            check=False,
        )
    if completed.returncode != 0:
        raise RuntimeError(
            f"harness exited with {completed.returncode}: {completed.stderr.strip()[-500:]}"
        )
    rows = json.loads(completed.stdout)
    by_id = {row["id"]: row for row in rows}
    results = []
    for job in jobs:
        row = by_id.get(job.job_id)
        if row is None:
            results.append(JobResult(job.job_id, error="missing from harness output"))
        else:
            results.append(JobResult(job.job_id, row.get("results", []), row.get("error")))
    return results


def run_jobs(
    jobs: Iterable[Job],
    *,
    hash_seed: int = 0,
    line_budget: int = DEFAULT_LINE_BUDGET,
    batch_size: int = 25,
    workers: int = 4,
    batch_timeout_s: float = DEFAULT_BATCH_TIMEOUT_S,
    job_timeout_s: float = DEFAULT_JOB_TIMEOUT_S,
) -> dict[str, JobResult]:
    """Run jobs in parallel batches; results are keyed by job id (order independent)."""
    jobs = list(jobs)
    if len({job.job_id for job in jobs}) != len(jobs):
        raise ValueError("job ids must be unique")
    batches = [jobs[i : i + batch_size] for i in range(0, len(jobs), batch_size)]

    def work(batch: list[Job]) -> list[JobResult]:
        try:
            return _run_batch(batch, hash_seed, line_budget, batch_timeout_s)
        except (subprocess.TimeoutExpired, RuntimeError, json.JSONDecodeError):
            retried = []
            for job in batch:
                try:
                    retried += _run_batch([job], hash_seed, line_budget, job_timeout_s)
                except subprocess.TimeoutExpired:
                    retried.append(JobResult(job.job_id, error="wall-clock timeout"))
                except (RuntimeError, json.JSONDecodeError) as exc:
                    retried.append(JobResult(job.job_id, error=f"harness failure: {exc}"))
            return retried

    output: dict[str, JobResult] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for batch_results in pool.map(work, batches):
            for result in batch_results:
                output[result.job_id] = result
    return output
