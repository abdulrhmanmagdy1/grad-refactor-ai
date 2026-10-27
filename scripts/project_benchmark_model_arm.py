"""Run the frozen project benchmark with another model (a model-size arm).

    python scripts/project_benchmark_model_arm.py --split test --name 14b \
        --model-config path/to/model.json --out path/to/folder

Everything the freeze record pins (dataset, review code, settings, matching) is checked
except the model, and the run is recorded as arm "full-<name>" with its own model
identity. The arm was added after the frozen 3B results were seen; it changes nothing but
the model, so it measures how much the model's size matters to the same pipeline. See
docs/evaluation/project-benchmark.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import project_benchmark as frozen  # noqa: E402

from refactor_ai.project import benchmark  # noqa: E402

MODEL_PROBLEM = "model differs from the freeze record"


def _freeze_machine_sha256(self) -> str:
    """BenchProject.sha256 with the file order of the machine the freeze was written on.

    The frozen sha256 sorts Path objects, and Windows paths compare case-insensitively
    while POSIX paths do not ("README.md" sorts after "hidden/" on Windows and before it
    on Linux), so the same files hash differently on Kaggle. This reproduces the Windows
    order on any platform; the files and the per-file hashes are the same.
    """
    digest = hashlib.sha256()
    paths = [p for p in self.root.rglob("*") if p.is_file()]
    for path in sorted(
        paths, key=lambda p: [part.lower() for part in p.relative_to(self.root).parts]
    ):
        relative = path.relative_to(self.root)
        if benchmark.SKIPPED_PARTS & set(relative.parts):
            continue
        digest.update(relative.as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(benchmark._normalized(path.read_bytes())).digest())
    return digest.hexdigest()


benchmark.BenchProject.sha256 = _freeze_machine_sha256


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--split", choices=benchmark.SPLITS, required=True)
    parser.add_argument("--name", required=True, help="short arm name, for example 14b")
    parser.add_argument("--model-config", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--project", action="append")
    args = parser.parse_args(argv)
    problems = []
    if args.split in benchmark.FROZEN_SPLITS:
        problems = frozen.freeze_problems(args.split, Path(args.model_config))
        other = [problem for problem in problems if problem != MODEL_PROBLEM]
        if other:
            print("The model arm runs only when everything but the model matches the freeze:")
            for problem in other:
                print(f"  {problem}")
            return 1
    code = frozen.command_run(
        argparse.Namespace(
            split=args.split,
            arm="full",
            project=args.project,
            model_config=args.model_config,
            out=args.out,
            allow_unfrozen=True,
        )
    )
    out = Path(args.out)
    run_path, records_path = out / "run.json", out / "records.jsonl"
    if run_path.is_file():
        run = json.loads(run_path.read_text(encoding="utf-8"))
        run.update(
            arm=f"full-{args.name}",
            model_arm=args.name,
            frozen=False,
            frozen_except_model=args.split in benchmark.FROZEN_SPLITS
            and problems in ([], [MODEL_PROBLEM]),
        )
        run_path.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8", newline="\n")
    if records_path.is_file():
        lines = records_path.read_text(encoding="utf-8").splitlines()
        records = [json.loads(line) for line in lines if line.strip()]
        for record in records:
            record["arm"] = f"full-{args.name}"
        records_path.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
            newline="\n",
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
