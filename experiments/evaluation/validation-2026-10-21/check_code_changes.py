"""Would the code changed since the Kaggle validation run change its numbers?

The validation run (kernel grad-refactor-ai-eval-600603dc) used a bundle built from commit
ee87a11 with an uncommitted working tree; see provenance.json for the file-by-file
comparison. This script answers the question without a model and without the test split:

1. it checks every file of this folder against outputs-manifest.json (the kernel's own
   SHA-256 list; CRLF is normalized to LF first, for Windows checkouts);
2. it regenerates the report from records.jsonl with the current report code and compares
   every table with the report produced on Kaggle;
3. it re-derives every deterministic decision from the recorded model outputs, once with
   the code of commit ee87a11 (taken from Git) and once with the current code: the parse
   of every analysis, refactoring and review output, the task rubric of every parsed
   proposal and of every final proposal, and the input check with its static findings for
   every validation case. Differences are listed per record.

Run from the repository root (writes nothing unless --out is given):

    python -m uv run python experiments/evaluation/validation-2026-10-21/check_code_changes.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EVALUATION_ID = "kaggle-grad-refactor-ai-eval-600603dc"
RECORDS = HERE / "evaluation" / EVALUATION_ID / "records.jsonl"
KAGGLE_REPORT = HERE / "report" / EVALUATION_ID
VALIDATION_COMMIT = "ee87a11ad2ede913c65c48664c8f131a5fe8aeb3"
UNDETERMINED_RULE = (
    "A record's outcome under the new code follows from its recorded model outputs when "
    "every decision the workflow acts on is unchanged: the parsed analysis, the parsed "
    "code, every rubric check, the test admission problems and the review verdict. Then "
    "every later prompt and the disposition are the same. When one of them changes (for "
    "example a rubric check, which decides whether a correction is requested and is "
    "quoted in the correction prompt), the later model outputs are unknown, so the "
    "outcome is undetermined until the arm is run again."
)
TABLES = (
    "arm_metrics.csv",
    "by_failure_type.csv",
    "by_source.csv",
    "by_source_group.csv",
    "paired.csv",
)


def lf_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def check_manifest() -> dict:
    manifest = json.loads((HERE / "outputs-manifest.json").read_text(encoding="utf-8"))
    bad = [
        rel
        for rel, digest in sorted(manifest.items())
        if hashlib.sha256(lf_bytes(HERE / rel)).hexdigest() != digest
    ]
    return {"files": len(manifest), "mismatches": bad}


def read_table(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def check_report() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "report_evaluation.py"),
                str(RECORDS),
                "--out",
                tmp,
            ],
            check=True,
            capture_output=True,
            cwd=ROOT,
        )
        differing = [
            name
            for name in TABLES
            if read_table(Path(tmp) / name) != read_table(KAGGLE_REPORT / name)
        ]
        old = json.loads((KAGGLE_REPORT / "report.json").read_text(encoding="utf-8"))
        new = json.loads((Path(tmp) / "report.json").read_text(encoding="utf-8"))
    return {
        "tables_compared": list(TABLES),
        "tables_differing": differing,
        "report_json_numbers_differing": numbers_differing(old, new),
    }


def numbers_differing(old, new, path="") -> list[str]:
    """Paths whose values differ; floats are compared to 1e-9 relative (summation order)."""
    if isinstance(old, dict) and isinstance(new, dict):
        keys = sorted(set(old) | set(new))
        return [
            d
            for key in keys
            for d in numbers_differing(old.get(key), new.get(key), f"{path}/{key}")
        ]
    if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        return [
            d
            for i, (a, b) in enumerate(zip(old, new, strict=True))
            for d in numbers_differing(a, b, f"{path}/{i}")
        ]
    if isinstance(old, float) and isinstance(new, float):
        return [] if abs(old - new) <= 1e-9 * max(1.0, abs(old)) else [path]
    return [] if old == new else [path]


def export_commit_src(commit: str, target: Path) -> Path:
    names = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", commit, "src/refactor_ai"],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    ).stdout.split()
    for name in names:
        if not name.endswith(".py"):
            continue
        data = subprocess.run(
            ["git", "show", f"{commit}:{name}"], check=True, capture_output=True, cwd=ROOT
        ).stdout
        out = target / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
    return target / "src"


def replay(src: Path, dataset: Path, out: Path) -> None:
    """Child mode: derive every deterministic decision with the code under src."""
    sys.path.insert(0, str(src))
    from refactor_ai import task_format
    from refactor_ai.agents import parsing
    from refactor_ai.tasks import guard_clauses
    from refactor_ai.verification import policy

    modules = (task_format, parsing, guard_clauses, policy)
    loaded = {getattr(m, "__file__", "") for m in modules}
    assert all(Path(f).resolve().is_relative_to(src.resolve()) for f in loaded), loaded

    def rows(path: Path) -> list[dict]:
        text = path.read_text(encoding="utf-8")
        return [json.loads(line) for line in text.split("\n") if line.strip()]

    def rubric(original: str, code: str) -> dict:
        result = guard_clauses.rubric(original, code)
        return {"passed": result.passed, "checks": dict(sorted(result.checks.items()))}

    cases = {row["id"]: row for row in rows(dataset) if row["split"] == "validation"}
    result = {"static": {}, "records": []}
    for case_id, row in sorted(cases.items()):
        check = guard_clauses.check_input(row["original_code"])
        result["static"][case_id] = {
            "supported": check.supported,
            "reasons": list(check.reasons),
            "opportunities": [
                [o.start_line, o.end_line, o.reason] for o in (check.opportunities or [])
            ],
        }
    for record in rows(RECORDS):
        original = cases[record["case_id"]]["original_code"]
        calls = []
        for call in record["calls"]:
            text, item = call.get("output"), {"index": call["index"], "role": call["role"]}
            if text is None:
                item["output"] = None
            elif call["role"] == "analysis":
                parsed = parsing.parse_analysis(text, len(original.splitlines()))
                report = parsed.report
                item.update(
                    error=parsed.error,
                    supported=report and report.supported_task,
                    findings=report
                    and [[f.start_line, f.end_line, f.reason] for f in report.findings],
                )
            elif call["role"] == "review":
                parsed = parsing.parse_review(text)
                item.update(
                    error=parsed.error, verdict=parsed.result and parsed.result.verdict.value
                )
            else:
                parsed = task_format.parse_refactor_output(text)
                item.update(
                    code=parsed.code,
                    error=parsed.error,
                    rubric=parsed.code and rubric(original, parsed.code),
                    admission=parsed.code and policy.admission_problems(parsed.code),
                )
            calls.append(item)
        proposed = record.get("proposed_code")
        result["records"].append(
            {
                "arm": record["arm"],
                "case_id": record["case_id"],
                "recorded": {
                    "rubric": record["rubric"],
                    "disposition": record["disposition"],
                    "proposal_ready": record["proposal_ready"],
                },
                "final_rubric": proposed and rubric(original, proposed),
                "final_admission": proposed and policy.admission_problems(proposed),
                "calls": calls,
            }
        )
    out.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")


def rubric_text(rubric: dict | None) -> str:
    if rubric is None:
        return "not scored"
    failed = ", ".join(sorted(name for name, ok in rubric["checks"].items() if not ok))
    return ("pass" if rubric["passed"] else "fail") + f" (failed checks: {failed or 'none'})"


def call_changes(old: dict, new: dict) -> tuple[list[str], bool]:
    """Changes of one call, and whether any of them is a decision the workflow acts on
    (parse result, rubric checks, test admission, review verdict) rather than wording."""
    where = f"call {old['index']} ({old['role']})"
    if old["role"] == "analysis":
        acted = [
            (
                "parsed analysis",
                (old.get("supported"), old.get("findings")),
                (new.get("supported"), new.get("findings")),
            )
        ]
    elif old["role"] == "review":
        acted = [("review verdict", old.get("verdict"), new.get("verdict"))]
    else:
        acted = [
            ("parsed code", old.get("code"), new.get("code")),
            ("rubric", old.get("rubric"), new.get("rubric")),
            ("test admission problems", old.get("admission"), new.get("admission")),
        ]
    changes = []
    for label, before, after in acted:
        if before != after:
            if label == "rubric":
                changes.append(f"{where}: rubric {rubric_text(before)} -> {rubric_text(after)}")
            else:
                changes.append(f"{where}: {label} differs")
    decision_changed = bool(changes)
    if not changes and old != new:
        changes.append(
            f"{where}: same outcome, different parse error text "
            f"({old.get('error')!r} -> {new.get('error')!r})"
        )
    return changes, decision_changed


def compare_replays(old: dict, new: dict) -> dict:
    static = sorted(case for case in old["static"] if old["static"][case] != new["static"][case])
    reproduced = [
        (r["arm"], r["case_id"])
        for r in old["records"]
        if r["final_rubric"] is not None
        and r["recorded"]["rubric"] != ("pass" if r["final_rubric"]["passed"] else "fail")
    ]
    affected = []
    undetermined: dict[str, list[str]] = {}
    for o, n in zip(old["records"], new["records"], strict=True):
        changes = []
        decision_changed = False
        if o["final_rubric"] != n["final_rubric"]:
            changes.append(
                f"final proposal: rubric {rubric_text(o['final_rubric'])} -> "
                f"{rubric_text(n['final_rubric'])}"
            )
        if o["final_admission"] != n["final_admission"]:
            changes.append(
                f"final proposal: test admission problems {o['final_admission']} -> "
                f"{n['final_admission']}"
            )
        decision_changed = bool(changes)
        for co, cn in zip(o["calls"], n["calls"], strict=True):
            call_messages, call_decision = call_changes(co, cn)
            changes += call_messages
            decision_changed = decision_changed or call_decision
        if changes:
            affected.append(
                {
                    "arm": o["arm"],
                    "case_id": o["case_id"],
                    "recorded": o["recorded"],
                    "changes": changes,
                    "outcome_determinable_under_new_code": not decision_changed,
                }
            )
        if decision_changed:
            undetermined.setdefault(o["arm"], []).append(o["case_id"])
    return {
        "bundle_replay_reproduces_recorded_rubric": not reproduced,
        "recorded_rubric_not_reproduced": reproduced,
        "validation_cases_with_different_input_check_or_static_findings": static,
        "records_with_differences": affected,
        "undetermined_rule": UNDETERMINED_RULE,
        "undetermined_records_by_arm": undetermined,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--out", type=Path, help="write the result as JSON here")
    parser.add_argument(
        "--replay", nargs=3, metavar=("SRC", "DATASET", "OUT"), help=argparse.SUPPRESS
    )
    args = parser.parse_args()
    if args.replay:
        replay(Path(args.replay[0]), Path(args.replay[1]), Path(args.replay[2]))
        return 0
    dataset = ROOT / "datasets" / "guard_clauses" / "v1" / "records.jsonl"
    result = {
        "evaluation_id": EVALUATION_ID,
        "manifest": check_manifest(),
        "report_with_current_code": check_report(),
    }
    with tempfile.TemporaryDirectory() as tmp:
        old_src = export_commit_src(VALIDATION_COMMIT, Path(tmp) / "old")
        outputs = {}
        for label, src in (("old", old_src), ("new", ROOT / "src")):
            outputs[label] = Path(tmp) / f"{label}.json"
            subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(Path(__file__).resolve()),
                    "--replay",
                    str(src),
                    str(dataset),
                    str(outputs[label]),
                ],
                check=True,
                cwd=tmp,
            )
        old = json.loads(outputs["old"].read_text(encoding="utf-8"))
        new = json.loads(outputs["new"].read_text(encoding="utf-8"))
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True, cwd=ROOT
    ).stdout.strip()
    result["replay"] = {
        "old_code": VALIDATION_COMMIT,
        "new_code": f"working tree at {head}",
        **compare_replays(old, new),
    }
    text = json.dumps(result, indent=2) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8", newline="\n")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
