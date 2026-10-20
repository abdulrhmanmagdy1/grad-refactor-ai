"""Build datasets/guard_clauses/v1 reproducibly.

Usage (from the repository root):

    python -m uv run python scripts/curate_dataset.py --download   # first run: fetch pinned sources
    python -m uv run python scripts/curate_dataset.py               # rebuild from data/raw/
    python -m uv run python scripts/curate_dataset.py --check       # verify committed files

The licensed sources are downloaded into the Git-ignored data/raw/ directory from URLs
pinned to a commit and verified by SHA-256. Rerunning with the same seed and inputs
reproduces every output except experiments/data/curation-run.json byte for byte.
--freeze-test records the test-split freeze. Once frozen, a run that would change the
test cases fails before writing; a run that changes only their rendering (a new prompt
version) needs --refreeze-rendering "<reason>", which keeps the previous freeze in the
record's history.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from refactor_ai.data.curate import DEFAULT_SEED, CurationConfig, curate  # noqa: E402
from refactor_ai.data.demo import build_demo_cases, demo_cases_json  # noqa: E402
from refactor_ai.data.manifest import (  # noqa: E402
    DEMO_PATH,
    FrozenSplitChanged,
    check_freeze,
    render_outputs,
    sha256_text,
    write_outputs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--download", action="store_true", help="download missing pinned sources")
    parser.add_argument("--freeze-test", action="store_true", help="record the test-split freeze")
    parser.add_argument(
        "--check",
        action="store_true",
        help="rebuild in memory and compare with the files on disk; writes nothing",
    )
    parser.add_argument(
        "--refreeze-rendering",
        metavar="REASON",
        help="accept a changed rendering (prompt format) of unchanged frozen test cases",
    )
    parser.add_argument(
        "--previous-records",
        type=Path,
        help="the frozen records file, needed once when the freeze record has no content hash",
    )
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    previous = args.previous_records.read_text(encoding="utf-8") if args.previous_records else None

    config = CurationConfig(
        root=ROOT, seed=args.seed, allow_download=args.download, workers=args.workers
    )
    demo_text = demo_cases_json(build_demo_cases(workers=args.workers))
    demo_file = ROOT / DEMO_PATH
    if not args.check:
        demo_file.parent.mkdir(parents=True, exist_ok=True)
        demo_file.write_text(demo_text, encoding="utf-8", newline="\n")
    result = curate(config)  # reads the demonstration cases for the independence check
    if args.check:
        outputs = render_outputs(result, ROOT)
        outputs[DEMO_PATH.as_posix()] = demo_text
        try:
            status = check_freeze(outputs, ROOT, previous_records_text=previous)
        except FrozenSplitChanged as exc:
            print(f"FROZEN TEST SPLIT CHANGED: {exc}")
            return 2
        if status.rendering_changed:
            print("FROZEN TEST SPLIT RENDERING CHANGED: cases unchanged, re-freeze needed")
            return 2
        differences = []
        for relative, text in outputs.items():
            path = ROOT / relative
            current = path.read_text(encoding="utf-8") if path.exists() else None
            if current is None or sha256_text(current) != sha256_text(text):
                differences.append(relative)
        for relative in differences:
            print(f"differs: {relative}")
        print("reproducible" if not differences else f"{len(differences)} file(s) differ")
        return 1 if differences else 0
    try:
        written = write_outputs(
            result,
            config,
            freeze_test=args.freeze_test,
            refreeze_reason=args.refreeze_rendering,
            previous_records_text=previous,
        )
    except FrozenSplitChanged as exc:
        print(f"Refusing to write: {exc}")
        return 2
    counts = {
        split: sum(r["split"] == split for r in result.records)
        for split in ("train", "validation", "test")
    }
    print(f"records: {len(result.records)} {counts}")
    for relative, digest in sorted(written.items()):
        print(f"{digest}  {relative}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
