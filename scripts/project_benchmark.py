"""Validate, freeze, run and report the seeded-project benchmark (protocol project-bench-v1).

    python -m uv run python scripts/project_benchmark.py validate --split dev
    python -m uv run python scripts/project_benchmark.py run --split dev --arm static
    python -m uv run python scripts/project_benchmark.py run --split dev --arm full \
        --model-config configs/model.project.local.json
    python -m uv run python scripts/project_benchmark.py freeze \
        --model-config configs/model.project.local.json
    python -m uv run python scripts/project_benchmark.py pairs RUN_DIR [RUN_DIR ...] \
        --out pairs.jsonl
    python -m uv run python scripts/project_benchmark.py report RUN_DIR [RUN_DIR ...] \
        [--labels labels.json]

The test split runs only when the freeze record matches the dataset, the code, the review
settings and the model; see docs/evaluation/project-benchmark.md.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import platform
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from refactor_ai.project import benchmark  # noqa: E402
from refactor_ai.project.review import ReviewSettings  # noqa: E402
from refactor_ai.project.testrun import ProjectTestRunner  # noqa: E402

RESULTS = ROOT / "experiments" / "evaluation" / "project-bench"
FREEZE = RESULTS / "freeze.json"


def freeze_path(split: str) -> Path:
    """The freeze record of a protected split (test: v1, test2: v2)."""
    return FREEZE if split == "test" else RESULTS / f"freeze-{split}.json"


ARMS = ("static", "full")
FROZEN_CODE = (
    "src/refactor_ai/project/*.py",
    "src/refactor_ai/providers/gguf.py",
    "src/refactor_ai/providers/gguf_worker.py",
    "scripts/project_benchmark.py",
)
MODEL_FIELDS = ("model_id", "model_revision", "gguf_file", "gguf_sha256", "context_tokens")


def review_settings() -> ReviewSettings:
    """The settings of both arms: the service defaults with the project's tests run."""
    return ReviewSettings(run_tests=True)


def code_hashes() -> dict[str, str]:
    files = sorted({path for pattern in FROZEN_CODE for path in ROOT.glob(pattern)})
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(
            path.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        for path in files
    }


def model_identity(config: Path) -> dict:
    data = json.loads(config.read_text(encoding="utf-8"))
    return {name: data.get(name) for name in MODEL_FIELDS}


def freeze_state(split: str, config: Path) -> dict:
    projects = benchmark.load_split(split, ROOT / benchmark.DATASET_ROOT)
    return {
        "protocol": benchmark.PROTOCOL_ID,
        "split": split,
        "projects": {project.name: project.sha256() for project in projects},
        "code": code_hashes(),
        "settings": dataclasses.asdict(review_settings()),
        "model": model_identity(config),
        "matching": {"line_tolerance": benchmark.LINE_TOLERANCE},
    }


def freeze_problems(split: str, config: Path) -> list[str]:
    path = freeze_path(split)
    if not path.is_file():
        return [f"{path.relative_to(ROOT).as_posix()} does not exist"]
    frozen = json.loads(path.read_text(encoding="utf-8"))
    current = freeze_state(split, config)
    return [
        f"{key} differs from the freeze record"
        for key in ("protocol", "split", "projects", "code", "settings", "model", "matching")
        if frozen.get(key) != current[key]
    ]


def git_state() -> dict:
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.stdout.strip()

    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}


def selected(split: str, names: list[str] | None) -> list[benchmark.BenchProject]:
    projects = benchmark.load_split(split, ROOT / benchmark.DATASET_ROOT)
    if names:
        missing = set(names) - {project.name for project in projects}
        if missing:
            raise SystemExit(f"unknown projects: {', '.join(sorted(missing))}")
        projects = [project for project in projects if project.name in names]
    if not projects:
        raise SystemExit(f"no benchmark projects in the {split} split")
    return projects


def command_validate(args: argparse.Namespace) -> int:
    runner = ProjectTestRunner()
    failed = 0
    for project in selected(args.split, args.project):
        result = benchmark.validate(project, runner, run_tests=not args.no_tests)
        print(f"{project.name}: {'ok' if result.ok else 'PROBLEMS'}")
        for note in result.notes:
            print(f"  note: {note}")
        for problem in result.problems:
            print(f"  problem: {problem}")
        failed += not result.ok
    return 1 if failed else 0


def command_freeze(args: argparse.Namespace) -> int:
    runner = ProjectTestRunner()
    for project in selected(args.split, None):
        if not benchmark.validate(project, runner).ok:
            print(f"{project.name} does not validate; nothing was frozen")
            return 1
    record = {
        **freeze_state(args.split, Path(args.model_config)),
        "frozen_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git": git_state(),
    }
    target = freeze_path(args.split)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {target.relative_to(ROOT).as_posix()}")
    return 0


def command_run(args: argparse.Namespace) -> int:
    config = Path(args.model_config)
    protected = args.split in benchmark.FROZEN_SPLITS
    frozen_problems = freeze_problems(args.split, config) if protected else []
    if frozen_problems and not args.allow_unfrozen:
        print("The test split runs only under the freeze record:")
        for problem in frozen_problems:
            print(f"  {problem}")
        return 1
    projects = selected(args.split, args.project)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.out) if args.out else RESULTS / f"{args.split}-{args.arm}-{stamp}"
    out.mkdir(parents=True, exist_ok=False)
    settings = review_settings()
    run = {
        "protocol": benchmark.PROTOCOL_ID,
        "split": args.split,
        "arm": args.arm,
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "projects": {project.name: project.sha256() for project in projects},
        "settings": dataclasses.asdict(settings),
        "model": model_identity(config) if args.arm == "full" else None,
        "frozen": protected and not frozen_problems,
        "freeze_problems": frozen_problems,
        "git": git_state(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
    }
    provider = None
    if args.arm == "full":
        from refactor_ai.providers.gguf import GgufProvider

        provider = GgufProvider.from_config(config)
    runner = ProjectTestRunner()
    records_path = out / "records.jsonl"
    try:
        with tempfile.TemporaryDirectory(prefix="project-bench-") as temp:
            for project in projects:
                print(f"{args.arm}: reviewing {project.name} ...", flush=True)
                record = benchmark.review_project(
                    project, provider, settings, runner, Path(temp), args.arm
                )
                with records_path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(json.dumps(record) + "\n")
                found = sum(1 for keys in record["matching"]["detected"].values() if keys)
                print(
                    f"  {found}/{len(project.manifest.issues)} issues found, "
                    f"{len(record['findings'])} findings, {len(record['fixes'])} fixes, "
                    f"{record['review_s']} s",
                    flush=True,
                )
    finally:
        if provider is not None:
            provider.close()
        run["finished_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        (out / "run.json").write_text(
            json.dumps(run, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    print(f"wrote {out.relative_to(ROOT).as_posix() if out.is_relative_to(ROOT) else out}")
    return 0


def load_run(folder: Path) -> tuple[dict, list[dict]]:
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    lines = (folder / "records.jsonl").read_text(encoding="utf-8").splitlines()
    return run, [json.loads(line) for line in lines if line.strip()]


def _percent(rate: dict) -> str:
    if rate["rate"] is None:
        return "n/a"
    low, high = rate["ci95"]
    return f"{rate['count']}/{rate['total']} ({rate['rate']:.0%}, {low:.0%} to {high:.0%})"


def render(
    runs: list[tuple[dict, list[dict]]],
    summaries: dict,
    comparison: dict | None,
    judged: dict | None = None,
) -> str:
    lines = [f"# {benchmark.PROTOCOL_ID} results", ""]
    for run, _ in runs:
        frozen = "frozen" if run["frozen"] else "not frozen"
        lines.append(
            f"- {run['split']} / {run['arm']}: started {run['started_at']}, commit "
            f"{run['git']['commit'][:10]}{' (dirty)' if run['git']['dirty'] else ''}, {frozen}"
        )
    lines += ["", "| | " + " | ".join(summaries) + " |", "|---|" + "---|" * len(summaries)]

    def row(label: str, value) -> None:
        lines.append(f"| {label} | " + " | ".join(value(s) for s in summaries.values()) + " |")

    row("Projects", lambda s: str(s["projects"]))
    row("Seeded issues located (a finding on the place)", lambda s: _percent(s["issues"]))
    categories = sorted({c for s in summaries.values() for c in s["issues_by_category"]})
    for category in categories:
        row(
            f"... {category}",
            lambda s, c=category: (
                _percent(s["issues_by_category"][c]) if c in s["issues_by_category"] else "n/a"
            ),
        )
    if all(s.get("confirmed") for s in summaries.values()):
        row(
            "Seeded issues found (judge confirmed)",
            lambda s: _percent(s["confirmed"]["issues"]),
        )
        for category in categories:
            row(
                f"... {category}",
                lambda s, c=category: (
                    _percent(s["confirmed"]["by_category"][c])
                    if c in s["confirmed"]["by_category"]
                    else "n/a"
                ),
            )
        row(
            "Located issues not judged yet",
            lambda s: str(s["confirmed"]["issues_located_but_not_judged"]),
        )
    row("Findings", lambda s: str(s["findings"]["total"]))
    row("... on a seeded issue", lambda s: _percent(s["findings"]["on_issue_share"]))
    row("... on a decoy", lambda s: str(s["findings"].get("on_decoy", 0)))
    row("... elsewhere (unlabelled)", lambda s: str(s["findings"].get("unlabelled", 0)))
    row("Decoys flagged", lambda s: _percent(s["decoys_hit"]))
    row(
        "Fixable issues fixed by the ready fixes",
        lambda s: _percent(s["fixable_issues"]["resolved_by_ready_fixes"]),
    )
    row(
        "Fixable issues fixed by some fix",
        lambda s: _percent(s["fixable_issues"]["resolved_by_some_fix"]),
    )
    row("Ready fixes", lambda s: str(s["ready_fixes"]))
    row("Ready fixes that break a test", lambda s: str(len(s["ready_harmful"])))
    row("Median review time (s)", lambda s: str(s["review_s"]["median"]))
    row("Model calls", lambda s: str(s["model_calls"]))
    for label, paired in (("located", comparison), ("judge confirmed", judged)):
        if not paired:
            continue
        lines += [
            "",
            f"Paired detection, {label} (first arm vs second arm, same issues): "
            f"both {paired['both']}, only first {paired['only_first']}, "
            f"only second {paired['only_second']}, neither {paired['neither']}, "
            f"exact McNemar p = {paired['mcnemar_p']}.",
        ]
    lines += ["", "## Per project", "", "| Arm | Project | Found | Missed | Decoys | Fixed |"]
    lines.append("|---|---|---|---|---|---|")
    for run, records in runs:
        for record in records:
            detected = record["matching"]["detected"]
            found = [i for i, keys in detected.items() if keys]
            missed = [i for i, keys in detected.items() if not keys]
            decoys = [d for d, keys in record["matching"]["decoys_hit"].items() if keys]
            fixed = record["fix_scores"].get("ready_together", {}).get("resolved", [])
            lines.append(
                f"| {run['arm']} | {record['project']} | {' '.join(found) or '-'} | "
                f"{' '.join(missed) or '-'} | {' '.join(decoys) or '-'} | "
                f"{' '.join(fixed) or '-'} |"
            )
    lines += ["", "## Fixes (disposition / outcome when applied alone)", ""]
    for arm, summary in summaries.items():
        table = ", ".join(f"{key}: {n}" for key, n in summary["fixes"].items()) or "none"
        lines.append(f"- {arm}: {table}")
    return "\n".join(lines) + "\n"


def load_runs(folders: list[str]) -> tuple[list, dict[str, benchmark.BenchProject]]:
    runs = [load_run(Path(folder)) for folder in folders]
    splits = {run["split"] for run, _ in runs}
    if len(splits) != 1:
        raise SystemExit("use runs of one split at a time")
    projects = {
        project.name: project
        for project in benchmark.load_split(splits.pop(), ROOT / benchmark.DATASET_ROOT)
    }
    return runs, projects


def command_pairs(args: argparse.Namespace) -> int:
    runs, projects = load_runs(args.runs)
    records = [record for _, record_list in runs for record in record_list]
    pairs = benchmark.adjudication_pairs(records, projects)
    out = Path(args.out)
    with out.open("w", encoding="utf-8", newline="\n") as handle:
        for pair in pairs:
            handle.write(json.dumps(pair) + "\n")
    print(f"wrote {len(pairs)} pairs to {out}")
    print(f"Judge instructions: {benchmark.JUDGE_INSTRUCTIONS}")
    return 0


def load_labels(path: str | None) -> dict[str, dict] | None:
    """{"labels": {pair_id: {"same": bool, "reason": str}}} written by the judge."""
    if not path:
        return None
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    labels = data["labels"]
    for key, value in labels.items():
        if not isinstance(value, dict) or not isinstance(value.get("same"), bool):
            raise SystemExit(f"label {key} has no boolean 'same'")
    return labels


def command_report(args: argparse.Namespace) -> int:
    runs, projects = load_runs(args.runs)
    manifests = {name: project.manifest for name, project in projects.items()}
    labels = load_labels(args.labels)
    summaries = {}
    for run, records in runs:
        label = run["arm"] if run["arm"] not in summaries else f"{run['arm']}-{run['started_at']}"
        summaries[label] = benchmark.summarize_arm(records, manifests, labels)
    comparison = judged = None
    if len(runs) == 2:
        comparison = benchmark.compare_detection(runs[0][1], runs[1][1], manifests)
        if labels is not None:
            judged = benchmark.compare_detection(runs[0][1], runs[1][1], manifests, labels)
    text = render(runs, summaries, comparison, judged)
    out = Path(args.out) if args.out else Path(args.runs[-1]) / "report.md"
    out.write_text(text, encoding="utf-8", newline="\n")
    (out.with_suffix(".json")).write_text(
        json.dumps(
            {"summaries": summaries, "paired": comparison, "paired_judged": judged}, indent=2
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="check benchmark projects")
    validate.add_argument("--split", choices=benchmark.SPLITS, default="dev")
    validate.add_argument("--project", action="append", help="one project (repeatable)")
    validate.add_argument("--no-tests", action="store_true", help="skip the test runs")
    validate.set_defaults(handler=command_validate)

    freeze = commands.add_parser("freeze", help="write the freeze record of a test split")
    freeze.add_argument("--split", choices=benchmark.FROZEN_SPLITS, default="test2")
    freeze.add_argument("--model-config", default="configs/model.project.local.json")
    freeze.set_defaults(handler=command_freeze)

    run = commands.add_parser("run", help="review the projects of a split with one arm")
    run.add_argument("--split", choices=benchmark.SPLITS, default="dev")
    run.add_argument("--arm", choices=ARMS, required=True)
    run.add_argument("--project", action="append", help="one project (repeatable)")
    run.add_argument("--model-config", default="configs/model.project.local.json")
    run.add_argument("--out", help="output folder (default: a new folder under the results)")
    run.add_argument("--allow-unfrozen", action="store_true", help="run the test split anyway")
    run.set_defaults(handler=command_run)

    pairs = commands.add_parser("pairs", help="export the (issue, finding) pairs to judge")
    pairs.add_argument("runs", nargs="+")
    pairs.add_argument("--out", required=True, help="JSONL file")
    pairs.set_defaults(handler=command_pairs)

    report = commands.add_parser("report", help="summarize run folders")
    report.add_argument("runs", nargs="+")
    report.add_argument("--labels", help="the judge's labels (JSON)")
    report.add_argument("--out", help="Markdown file (default: report.md in the last run)")
    report.set_defaults(handler=command_report)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
