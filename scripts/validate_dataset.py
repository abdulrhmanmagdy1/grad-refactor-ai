"""Validate JSONL fields, exact normalized duplicates, and source-group separation.

load_and_validate(path) is the original check and stays standard-library only, because
training/train_lora.py imports it in the training environment. The optional extended
checks (--extended, validate_extended) need the core environment: they verify the
dataset-record contract of docs/architecture/contracts.md for every record, cross-split
near-duplicates, and optionally the manifest hashes, the test-split freeze and external
fixtures (for example the models workstream's pilot functions).
"""

import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

REQUIRED = ("id", "source_group", "split", "prompt", "completion", "license", "refactoring_type")
EXTENDED = (
    "original_code",
    "target_code",
    "function_name",
    "tests",
    "source",
    "source_url",
    "provenance",
    "prompt_version",
    "task_version",
)
CASE_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,95}$")
SPLIT_NAMES = ("train", "validation", "test")


def load_and_validate(path: Path) -> list[dict]:
    records = []
    ids = set()
    groups = {}
    prompts = set()
    completions = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"Line {number}: expected an object")
        if any(not isinstance(row.get(k), str) or not row[k].strip() for k in REQUIRED):
            raise ValueError(f"Line {number}: missing or blank required string")
        if row["split"] not in {"train", "validation", "test"}:
            raise ValueError(f"Line {number}: invalid split")
        if row["id"] in ids:
            raise ValueError(f"Line {number}: duplicate id")
        ids.add(row["id"])
        group, split = row["source_group"], row["split"]
        if groups.setdefault(group, split) != split:
            raise ValueError(f"Line {number}: source_group crosses splits")
        prompt = hashlib.sha256(" ".join(row["prompt"].split()).encode()).hexdigest()
        if prompt in prompts:
            raise ValueError(f"Line {number}: duplicate normalized prompt")
        prompts.add(prompt)
        completion = hashlib.sha256(" ".join(row["completion"].split()).encode()).hexdigest()
        if completions.setdefault(completion, split) != split:
            raise ValueError(f"Line {number}: completion crosses splits")
        records.append(row)
    if not records:
        raise ValueError("Dataset is empty")
    if not {"train", "validation", "test"}.issubset({r["split"] for r in records}):
        raise ValueError("Expected non-empty train, validation and test splits")
    return records


def _import_core():
    """Import the shared task modules; the extended checks need the core environment."""
    src = Path(__file__).resolve().parents[1] / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from refactor_ai import task_format
    from refactor_ai.contracts import ReferenceTest
    from refactor_ai.tasks import guard_clauses

    return task_format, guard_clauses, ReferenceTest


def _check_record(row: dict, task_format, guard_clauses, reference_test) -> list[str]:
    problems = []
    rid = row.get("id", "?")
    missing = [key for key in EXTENDED if key not in row]
    if missing:
        return [f"{rid}: missing fields {missing}"]
    if not CASE_ID.match(rid):
        problems.append(f"{rid}: id is not a valid reference case id")
    if row["refactoring_type"] != guard_clauses.TASK_TYPE:
        problems.append(f"{rid}: refactoring_type is not {guard_clauses.TASK_TYPE}")
    if row["prompt_version"] != task_format.PROMPT_VERSION:
        problems.append(f"{rid}: prompt_version {row['prompt_version']!r}")
    if row["task_version"] != guard_clauses.TASK_VERSION:
        problems.append(f"{rid}: task_version {row['task_version']!r}")
    for key in ("source", "source_url", "provenance", "function_name"):
        if not isinstance(row[key], str) or not row[key].strip():
            problems.append(f"{rid}: {key} must be a non-blank string")
    original, target = row["original_code"], row["target_code"]
    check = guard_clauses.check_input(original)
    if not check.supported:
        problems.append(f"{rid}: original is outside the task scope ({check.reasons})")
        return problems
    if check.function_name != row["function_name"]:
        problems.append(f"{rid}: function_name does not match the code")
    if guard_clauses.to_guard_clauses(original) != target:
        problems.append(f"{rid}: target_code is not the reference transformation")
    if not guard_clauses.rubric(original, target).passed:
        problems.append(f"{rid}: target_code fails the rubric")
    findings = [
        {"start_line": o.start_line, "end_line": o.end_line, "reason": o.reason}
        for o in check.opportunities
    ]
    allowed_prompts = {
        task_format.build_refactor_user_prompt(original),
        task_format.build_refactor_user_prompt(original, findings),
    }
    if row["prompt"] not in allowed_prompts:
        problems.append(f"{rid}: prompt is not the refactor prompt for original_code")
    if row["split"] != "train" and "Analysis notes:" in row["prompt"]:
        problems.append(f"{rid}: analysis notes are only used in the training split")
    parsed = task_format.parse_refactor_output(row["completion"])
    if parsed.error or parsed.repaired or not parsed.explanation:
        problems.append(f"{rid}: completion does not parse cleanly")
    elif parsed.code != target.rstrip() + "\n":
        problems.append(f"{rid}: completion code differs from target_code")
    tests = row["tests"]
    if not isinstance(tests, list) or not tests:
        problems.append(f"{rid}: tests must be a non-empty list")
        return problems
    for index, item in enumerate(tests):
        try:
            test = reference_test.model_validate(item)
            args = ast.literal_eval(test.args)
            kwargs = ast.literal_eval(test.kwargs)
        except Exception as exc:  # report any malformed test instead of stopping
            problems.append(f"{rid}: test {index} is invalid: {exc}")
            continue
        if not isinstance(args, list) or not isinstance(kwargs, dict):
            problems.append(f"{rid}: test {index} args/kwargs must be a list and a dict")
        if test.expect.kind == "return":
            try:
                ast.literal_eval(test.expect.value or "")
            except (ValueError, SyntaxError):
                problems.append(f"{rid}: test {index} expected value is not a literal")
        elif not (test.expect.exception or "").isidentifier():
            problems.append(f"{rid}: test {index} expected exception is not a name")
    return problems


def validate_extended(
    records: list[dict],
    *,
    near_duplicates: bool = True,
    external: list[Path] | None = None,
    root: Path | None = None,
) -> dict:
    """Contract checks for every record plus leakage checks; raises ValueError on problems."""
    task_format, guard_clauses, reference_test = _import_core()
    problems: list[str] = []
    for row in records:
        problems += _check_record(row, task_format, guard_clauses, reference_test)
    summary: dict = {"records_checked": len(records)}
    if near_duplicates or external:
        from refactor_ai.data import leakage

        prints = {
            field: [
                leakage.Fingerprint.of(r["id"], r["split"], r["source_group"], r[field])
                for r in records
            ]
            for field in ("original_code", "target_code")
        }
        if near_duplicates:
            examined = 0
            for field, items in prints.items():
                for left_split, right_split in (
                    ("train", "validation"),
                    ("train", "test"),
                    ("validation", "test"),
                ):
                    report = leakage.compare(
                        [p for p in items if p.split == left_split],
                        [p for p in items if p.split == right_split],
                    )
                    examined += report.pairs_examined
                    problems += [
                        f"near-duplicate across splits ({field}): {pair.left} vs {pair.right}"
                        for pair in report.flagged
                    ]
            summary["cross_split_pairs_examined"] = examined
        if external:
            base = root or Path.cwd()
            codes, inventory = leakage.external_code(external, base)
            outside = [
                leakage.Fingerprint.of(label, "external", "external", c) for label, c in codes
            ]
            examined = 0
            for field, items in prints.items():
                heldout = [p for p in items if p.split != "train"]
                report = leakage.compare(heldout, outside, skip_same_split=False)
                examined += report.pairs_examined
                problems += [
                    f"held-out record {pair.left} near-duplicates external {pair.right} ({field})"
                    for pair in report.flagged
                ]
            summary["external_files"] = len(inventory)
            summary["external_functions"] = len(codes)
            summary["external_pairs_examined"] = examined
    if problems:
        shown = "\n".join(problems[:50])
        raise ValueError(f"{len(problems)} extended check(s) failed:\n{shown}")
    return summary


def split_sha256(path: Path, split: str) -> str:
    """Hash of one split: its JSON lines in file order, LF-terminated (see the manifest)."""
    lines = [
        line
        for line in path.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
        if line.strip() and json.loads(line)["split"] == split
    ]
    return hashlib.sha256("".join(line + "\n" for line in lines).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(
        path.read_text(encoding="utf-8").replace("\r\n", "\n").encode()
    ).hexdigest()


def _content_module():
    """refactor_ai.data.content (standard library only), imported on demand."""
    src = Path(__file__).resolve().parents[1] / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from refactor_ai.data import content

    return content


def content_sha256(path: Path, split: str | None = None) -> str:
    """Case-content hash (independent of prompt rendering), see refactor_ai.data.content."""
    content = _content_module()
    rows = content.records_from_text(path.read_text(encoding="utf-8"))
    return content.content_sha256(rows, split)


def verify_manifest(path: Path, manifest_path: Path) -> list[str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    problems = []
    if file_sha256(path) != manifest["files"]["records"]["sha256"]:
        problems.append("records file hash differs from the manifest")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    for split in SPLIT_NAMES:
        entry = manifest["splits"][split]
        if split_sha256(path, split) != entry["sha256"]:
            problems.append(f"{split} split hash differs from the manifest")
        if [r["id"] for r in rows if r["split"] == split] != entry["ids"]:
            problems.append(f"{split} split ids differ from the manifest")
        if "content_sha256" in entry and content_sha256(path, split) != entry["content_sha256"]:
            problems.append(f"{split} split case content differs from the manifest")
    return problems


def verify_freeze(path: Path, freeze_path: Path) -> list[str]:
    frozen = json.loads(freeze_path.read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    problems = []
    if split_sha256(path, "test") != frozen["split_sha256"]:
        problems.append("test split hash differs from the frozen hash")
    if [r["id"] for r in rows if r["split"] == "test"] != frozen["ids"]:
        problems.append("test split ids differ from the frozen ids")
    if "content_sha256" in frozen and content_sha256(path, "test") != frozen["content_sha256"]:
        problems.append("test split case content differs from the frozen content")
    return problems


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--extended", action="store_true", help="dataset-record contract and near-duplicate checks"
    )
    parser.add_argument("--manifest", type=Path, help="verify hashes and ids against a manifest")
    parser.add_argument("--freeze", type=Path, help="verify the test split against a freeze record")
    parser.add_argument(
        "--external",
        type=Path,
        nargs="*",
        default=None,
        help="fixture files or folders that held-out records must not near-duplicate",
    )
    args = parser.parse_args()
    rows = load_and_validate(args.path)
    report = {
        "records": len(rows),
        "splits": {s: sum(r["split"] == s for r in rows) for s in ("train", "validation", "test")},
    }
    failures = []
    if args.extended or args.external:
        try:
            report["extended"] = validate_extended(
                rows, near_duplicates=args.extended, external=args.external, root=Path.cwd()
            )
        except ValueError as exc:
            failures.append(str(exc))
    if args.manifest:
        failures += verify_manifest(args.path, args.manifest)
    if args.freeze:
        failures += verify_freeze(args.path, args.freeze)
    if args.manifest or args.freeze or args.extended:
        report["split_sha256"] = {s: split_sha256(args.path, s) for s in SPLIT_NAMES}
    print(json.dumps(report, indent=2))
    if failures:
        print("\n".join(failures), file=sys.stderr)
        raise SystemExit(1)
