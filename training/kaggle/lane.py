"""Kaggle lane: run training and evaluations on Kaggle's free GPU.

Run with the system Python that has uv (standard library only), from the repository root:

    python training/kaggle/lane.py bundle [--adapter runs/training/<run>/adapter]
    python training/kaggle/lane.py upload
    python training/kaggle/lane.py push --job smoke --case-ids ID1 ID2 --arms A
    python training/kaggle/lane.py wait <slug>
    python training/kaggle/lane.py fetch <slug>

Everything on Kaggle is PRIVATE: the bundle dataset and every kernel. The Kaggle CLI is
called through `python -m uv tool run --from kaggle kaggle` with the token in
~/.kaggle/access_token (never printed). See training/kaggle/README.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RUNS = ROOT / "runs" / "kaggle"
STAGE = RUNS / "stage"
KERNELS = RUNS / "kernels"
SUBMISSIONS = RUNS / "submissions.jsonl"
STATE = HERE / "bundle-state.json"
OWNER = "abdelrhmanadel208"
DATASET = f"{OWNER}/grad-refactor-ai-bundle"
ACCELERATOR = "NvidiaTeslaT4"
KAGGLE = [sys.executable, "-m", "uv", "tool", "run", "--from", "kaggle", "kaggle"]
TERMINAL = ("complete", "error", "cancelacknowledged", "cancel_acknowledged")
BUNDLE_FILES = (
    "pyproject.toml",
    "uv.lock",
    "src/refactor_ai/**/*.py",
    "src/refactor_ai/fixtures/*.json",
    "scripts/*.py",
    "datasets/guard_clauses/v1/records.jsonl",
    "datasets/guard_clauses/v1/manifest.json",
    "datasets/guard_clauses/v1/metadata.jsonl",
    "datasets/guard_clauses/v1/NOTICE.md",
    "configs/training.full.json",
    "configs/model.example.json",
    "training/train_lora.py",
    "training/common.py",
    "training/requirements-cuda.txt",
    "training/kaggle/kernel_template.py",
    "training/kaggle/bench_kernel.py",
    "datasets/project_bench/v1/**/*",
    "experiments/evaluation/project-bench/freeze*.json",
    "experiments/evaluation/protocol-freeze.json",
    "experiments/data/test-split-freeze.json",
)
ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def kaggle(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    process = subprocess.run(
        [*KAGGLE, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and process.returncode != 0:
        raise SystemExit(f"kaggle {' '.join(args)} failed:\n{process.stdout}\n{process.stderr}")
    return process


def note(event: str, **fields) -> None:
    RUNS.mkdir(parents=True, exist_ok=True)
    entry = {"event": event, "at": datetime.now(UTC).isoformat(timespec="seconds"), **fields}
    with SUBMISSIONS.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
    print(json.dumps(entry))


def git(*args: str) -> str:
    process = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return process.stdout.strip()


def bundle(adapter: Path | None) -> dict:
    files: dict[str, Path] = {}
    for pattern in BUNDLE_FILES:
        for path in sorted(ROOT.glob(pattern)):
            if path.is_file() and "__pycache__" not in path.parts:
                files[path.relative_to(ROOT).as_posix()] = path
    repo_files = set(files)
    if adapter is not None:
        for path in sorted(adapter.iterdir()):
            if path.is_file() and path.suffix != ".bin":  # training_args.bin is a pickle
                files[f"adapter/{path.name}"] = path
    hashes = {name: sha256_file(path) for name, path in sorted(files.items())}
    bundle_sha = sha256_bytes("".join(f"{h}  {n}\n" for n, h in hashes.items()).encode())
    manifest = {
        "bundle_sha256": bundle_sha,
        "git_head": git("rev-parse", "HEAD"),
        # Only the bundled repository files matter for the bundle's provenance; edits
        # elsewhere in the working tree (for example frontend/) do not make it dirty.
        # One status call for the whole tree, filtered to the bundled files (passing every
        # file as an argument outgrows the Windows command-line limit).
        "git_dirty": any(
            line[3:].strip().strip('"') in repo_files
            for line in git("status", "--porcelain", "--untracked-files=all").splitlines()
        ),
        "adapter": None if adapter is None else adapter.relative_to(ROOT).as_posix(),
        "files": hashes,
    }
    STAGE.mkdir(parents=True, exist_ok=True)
    for old in STAGE.iterdir():
        old.unlink()
    with zipfile.ZipFile(STAGE / "bundle.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name, path in sorted(files.items()):
            info = zipfile.ZipInfo(name, ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
        info = zipfile.ZipInfo("bundle-manifest.json", ZIP_TIME)
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, json.dumps(manifest, indent=2))
    (STAGE / "bundle-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (STAGE / "dataset-metadata.json").write_text(
        json.dumps(
            {"title": "grad-refactor-ai-bundle", "id": DATASET, "licenses": [{"name": "other"}]}
        ),
        encoding="utf-8",
    )
    summary = {
        "bundle_sha256": bundle_sha,
        "files": len(hashes),
        "zip_bytes": (STAGE / "bundle.zip").stat().st_size,
        "zip_sha256": sha256_file(STAGE / "bundle.zip"),
        "adapter": manifest["adapter"],
        "git_head": manifest["git_head"],
        "git_dirty": manifest["git_dirty"],
    }
    note("bundle", **summary)
    return summary


def upload() -> None:
    manifest = json.loads((STAGE / "bundle-manifest.json").read_text(encoding="utf-8"))
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    exists = kaggle("datasets", "status", DATASET, check=False).returncode == 0
    if exists and state.get("bundle_sha256") == manifest["bundle_sha256"]:
        note("upload-skipped", bundle_sha256=manifest["bundle_sha256"], reason="unchanged")
        return
    if exists:
        kaggle(
            "datasets",
            "version",
            "-p",
            str(STAGE),
            "-m",
            f"bundle {manifest['bundle_sha256'][:12]}",
            "--dir-mode",
            "skip",
        )
    else:  # 'datasets create' is private unless --public is given
        kaggle("datasets", "create", "-p", str(STAGE), "--dir-mode", "skip")
    deadline = time.time() + 1800
    status = ""
    while time.time() < deadline:
        status = kaggle("datasets", "status", DATASET, check=False).stdout.strip()
        if status == "ready":
            break
        time.sleep(20)
    if status != "ready":
        raise SystemExit(f"dataset not ready after 30 min: {status!r}")
    state = {
        "dataset": DATASET,
        "private": True,
        "bundle_sha256": manifest["bundle_sha256"],
        "zip_sha256": sha256_file(STAGE / "bundle.zip"),
        "adapter": manifest["adapter"],
        "git_head": manifest["git_head"],
        "git_dirty": manifest["git_dirty"],
        "uploaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    note("upload", **state)


def push(args) -> str:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    if args.job == "bench":
        return push_bench(args, state)
    if args.split == "test":
        # The single final evaluation: only on demand, against a frozen protocol, and
        # from a bundle built from a committed, clean tree so the code is identifiable.
        if args.job != "eval" or not args.i_confirm_frozen_test or not args.protocol_version:
            raise SystemExit(
                "a test-split job needs --job eval, --i-confirm-frozen-test and --protocol-version"
            )
        if state.get("git_dirty", True):
            raise SystemExit("rebuild the bundle from a clean, committed tree for the test split")
    job = {
        "kind": "train" if args.job == "train" else "eval",
        "name": args.job,
        "split": args.split,
        "protocol_version": args.protocol_version,
        "bundle_sha256": state["bundle_sha256"],
        "arms": args.arms,
        "case_ids": args.case_ids or [],
        "run_id": args.run_id,
        "adapter_id": args.adapter_id,
        "adapter_sha256": args.adapter_sha256,
        "adapter_config_sha256": args.adapter_config_sha256,
    }
    key = sha256_bytes(json.dumps(job, sort_keys=True).encode())[:8]
    slug = f"grad-refactor-ai-{args.job}-{key}"
    job["evaluation_id"] = f"kaggle-{slug}"
    folder = KERNELS / slug
    folder.mkdir(parents=True, exist_ok=True)
    template = (HERE / "kernel_template.py").read_text(encoding="utf-8")
    marker = "JOB = {}  # replaced by lane.py"
    if template.count(marker) != 1:
        raise SystemExit("the kernel template has no JOB marker")
    # A JSON string literal is valid Python; json.loads turns it back into the job.
    source = template.replace(marker, f"JOB = json.loads({json.dumps(json.dumps(job))})")
    (folder / "run.py").write_text(source, encoding="utf-8", newline="\n")
    metadata = {
        "id": f"{OWNER}/{slug}",
        "title": slug,
        "code_file": "run.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": True,
        "enable_tpu": False,
        "enable_internet": True,
        "machine_shape": ACCELERATOR,
        "dataset_sources": [DATASET],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }
    (folder / "kernel-metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    result = kaggle(
        "kernels",
        "push",
        "-p",
        str(folder),
        "-t",
        str(args.timeout_min * 60),
        "--accelerator",
        ACCELERATOR,
    )
    note("push", slug=slug, job=job, cli=result.stdout.strip()[-300:])
    return slug


def push_bench(args, state: dict) -> str:
    """The project benchmark with a larger model (training/kaggle/bench_kernel.py)."""
    if args.bench_split in ("test", "test2", "test3") and state.get("git_dirty", True):
        raise SystemExit("rebuild the bundle from a clean, committed tree for the test split")
    job = {
        "kind": "bench",
        "split": args.bench_split,
        "model": args.model,
        "projects": args.projects or [],
        "bundle_sha256": state["bundle_sha256"],
    }
    key = sha256_bytes(json.dumps(job, sort_keys=True).encode())[:8]
    slug = f"grad-refactor-ai-bench-{args.model}-{key}"
    return push_kernel(slug, job, "bench_kernel.py", args.timeout_min)


def push_kernel(slug: str, job: dict, template_name: str, timeout_min: int) -> str:
    folder = KERNELS / slug
    folder.mkdir(parents=True, exist_ok=True)
    template = (HERE / template_name).read_text(encoding="utf-8")
    marker = "JOB = {}  # replaced by lane.py"
    if template.count(marker) != 1:
        raise SystemExit("the kernel template has no JOB marker")
    source = template.replace(marker, f"JOB = json.loads({json.dumps(json.dumps(job))})")
    (folder / "run.py").write_text(source, encoding="utf-8", newline="\n")
    metadata = {
        "id": f"{OWNER}/{slug}",
        "title": slug,
        "code_file": "run.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": True,
        "enable_tpu": False,
        "enable_internet": True,
        "machine_shape": ACCELERATOR,
        "dataset_sources": [DATASET],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }
    (folder / "kernel-metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    result = kaggle(
        "kernels",
        "push",
        "-p",
        str(folder),
        "-t",
        str(timeout_min * 60),
        "--accelerator",
        ACCELERATOR,
    )
    note("push", slug=slug, job=job, cli=result.stdout.strip()[-300:])
    return slug


def wait(slug: str, poll_s: int = 60, limit_min: int = 600) -> str:
    started = time.time()
    last = None
    while time.time() - started < limit_min * 60:
        process = kaggle("kernels", "status", f"{OWNER}/{slug}", check=False)
        text = (process.stdout + process.stderr).strip()
        status = text.split('status "')[-1].split('"')[0].lower() if 'status "' in text else text
        if status != last:
            note(
                "status",
                slug=slug,
                status=status,
                elapsed_min=round((time.time() - started) / 60, 1),
            )
            last = status
        if any(word in status for word in TERMINAL):
            return status
        time.sleep(poll_s)
    return last or "unknown"


def fetch(slug: str) -> Path:
    kind = "training" if "-train-" in slug else "evaluation"
    if "-bench-" in slug:
        kind = "bench"
    destination = ROOT / "runs" / kind / f"kaggle-{slug}"
    destination.mkdir(parents=True, exist_ok=True)
    kaggle("kernels", "output", f"{OWNER}/{slug}", "-p", str(destination), "-o")
    manifest_path = destination / "outputs-manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"no outputs-manifest.json in {destination}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing = [name for name in manifest if not (destination / name).exists()]
    mismatched = [
        name
        for name, sha in manifest.items()
        if (destination / name).exists() and sha256_file(destination / name) != sha
    ]
    note(
        "fetch",
        slug=slug,
        destination=destination.relative_to(ROOT).as_posix(),
        files=len(manifest),
        missing=missing,
        mismatched=mismatched,
    )
    if missing or mismatched:
        raise SystemExit("downloaded outputs do not match the kernel's manifest")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("bundle")
    b.add_argument("--adapter", type=Path)
    sub.add_parser("upload")
    p = sub.add_parser("push")
    p.add_argument("--job", choices=("smoke", "train", "eval", "bench"), required=True)
    p.add_argument("--model", choices=("14b", "32b"), default="14b", help="bench only")
    p.add_argument(
        "--bench-split", choices=("dev", "test", "test2", "test3"), default="dev", help="bench only"
    )
    p.add_argument("--projects", nargs="*", help="bench only: a subset of the split")
    p.add_argument("--arms", default="A,B,C,D")
    p.add_argument("--case-ids", nargs="*")
    p.add_argument("--run-id", default="full-2026-10-20")
    p.add_argument("--adapter-id")
    p.add_argument("--adapter-sha256")
    p.add_argument("--adapter-config-sha256")
    p.add_argument("--timeout-min", type=int, default=240)
    p.add_argument("--split", choices=("validation", "test"), default="validation")
    p.add_argument("--i-confirm-frozen-test", action="store_true")
    p.add_argument("--protocol-version")
    w = sub.add_parser("wait")
    w.add_argument("slug")
    w.add_argument("--poll-s", type=int, default=60)
    f = sub.add_parser("fetch")
    f.add_argument("slug")
    args = parser.parse_args()
    if args.command == "bundle":
        bundle(args.adapter.resolve() if args.adapter else None)
    elif args.command == "upload":
        upload()
    elif args.command == "push":
        print(push(args))
    elif args.command == "wait":
        print(wait(args.slug, args.poll_s))
    elif args.command == "fetch":
        print(fetch(args.slug))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
