"""Build ``RELEASE_MANIFEST.json``: sha256 checksums for the release artifacts.

The manifest covers exactly the artifacts quoted by the delivery records:

- ``dataset``        - ``data/curated.jsonl`` and ``data/manifest.json``;
- ``experiments``    - top-level CSV/JSON files under ``experiments/``
                       (review-packet inputs are excluded on purpose);
- ``frontend_dist``  - every file of the committed UI bundle ``frontend/dist``.

Each file gets a sha256; every group and the whole artifact set get an
aggregate digest over sorted ``"<path> <sha256>"`` lines. The script also
prints a Markdown checksum block ready to paste into the GitHub Release notes.
Regenerate it after any artifact change and *before* tagging a release, then
run ``scripts/verify_release.py`` (also from the second machine of the clean
clone check) to prove the working tree matches the release.
"""

import argparse
import hashlib
import json
import sys
import time
import tomllib
from pathlib import Path

GROUP_DATASET = "dataset"
GROUP_EXPERIMENTS = "experiments"
GROUP_FRONTEND = "frontend_dist"
GROUPS = (GROUP_DATASET, GROUP_EXPERIMENTS, GROUP_FRONTEND)

DATASET_FILES = ("data/curated.jsonl", "data/manifest.json")
EXPERIMENT_PATTERNS = ("experiments/*.csv", "experiments/*.json")
FRONTEND_DIST_DIR = "frontend/dist"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_artifacts(root: Path) -> dict[str, str]:
    """Map posix relative path -> group for every release artifact."""
    artifacts: dict[str, str] = {}
    for rel in DATASET_FILES:
        if (root / rel).exists():
            artifacts[rel] = GROUP_DATASET
    for pattern in EXPERIMENT_PATTERNS:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                artifacts[path.relative_to(root).as_posix()] = GROUP_EXPERIMENTS
    dist = root / FRONTEND_DIST_DIR
    if dist.exists():
        for path in sorted(p for p in dist.rglob("*") if p.is_file()):
            artifacts[path.relative_to(root).as_posix()] = GROUP_FRONTEND
    return dict(sorted(artifacts.items()))


def group_digest(entries: list[tuple[str, str]]) -> str:
    """Deterministic aggregate digest over sorted ``"<path> <sha256>"`` lines."""
    payload = "\n".join(f"{path} {sha}" for path, sha in sorted(entries))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_manifest(root: Path, version: str) -> dict:
    artifacts: list[dict] = []
    for rel, group in collect_artifacts(root).items():
        path = root / rel
        artifacts.append(
            {
                "path": rel,
                "group": group,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )

    groups: dict[str, dict] = {}
    for group in GROUPS:
        members = [
            (entry["path"], entry["sha256"]) for entry in artifacts if entry["group"] == group
        ]
        groups[group] = {
            "artifact_count": len(members),
            "aggregate_sha256": group_digest(members) if members else None,
        }

    return {
        "version": version,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "aggregate_sha256": group_digest([(e["path"], e["sha256"]) for e in artifacts]),
        "artifact_count": len(artifacts),
        "groups": groups,
        "artifacts": artifacts,
    }


def project_version(root: Path) -> str:
    with open(root / "pyproject.toml", "rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def markdown_block(manifest: dict) -> str:
    lines = [
        f"### Release checksums (v{manifest['version']}, generated {manifest['generated_at']})",
        "",
        "| Group | Files | SHA-256 |",
        "|---|---|---|",
    ]
    for group, stats in manifest["groups"].items():
        lines.append(f"| `{group}` | {stats['artifact_count']} | `{stats['aggregate_sha256']}` |")
    lines.append("")
    lines.append(
        f"Aggregate: `{manifest['aggregate_sha256']}` (full list in RELEASE_MANIFEST.json)."
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1], help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Defaults to <root>/RELEASE_MANIFEST.json.",
    )
    args = parser.parse_args()

    manifest = build_manifest(args.root, project_version(args.root))
    output = args.output or (args.root / "RELEASE_MANIFEST.json")
    output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Manifest written to {output} ({manifest['artifact_count']} artifacts).")
    print(markdown_block(manifest))


if __name__ == "__main__":
    sys.exit(main())
