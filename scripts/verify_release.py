"""Verify the working tree against ``RELEASE_MANIFEST.json`` (delivery checklist).

Recomputes every artifact hash recorded by ``scripts/make_release.py`` and the
group/aggregate digests, and reports:

- ``missing``  artifacts the manifest lists but the tree does not have;
- ``changed``  artifacts whose bytes differ from the recorded sha256;
- ``extra``    files present in a tracked group but absent from the manifest;
- group digests that no longer match their file lists.

Exit code 0 means the tree matches the manifest exactly — the check to run on
the second machine of the clean-clone verification (and in CI before a tag).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_release import build_manifest, collect_artifacts, sha256_file  # noqa: E402


def verify(root: Path, manifest: dict) -> list[str]:
    """Return a list of human-readable problems; empty means the tree matches."""
    problems: list[str] = []
    recorded = {entry["path"]: entry for entry in manifest["artifacts"]}
    current = collect_artifacts(root)

    for rel, entry in sorted(recorded.items()):
        path = root / rel
        if not path.exists():
            problems.append(f"missing: {rel}")
            continue
        digest = sha256_file(path)
        if digest != entry["sha256"]:
            problems.append(
                f"changed: {rel} (expected {entry['sha256'][:12]}…, found {digest[:12]}…)"
            )

    for rel in sorted(set(current) - set(recorded)):
        problems.append(f"extra: {rel} (group {current[rel]})")

    fresh = build_manifest(root, manifest.get("version", "unknown"))
    for group, stats in manifest.get("groups", {}).items():
        fresh_stats = fresh["groups"].get(group, {})
        if stats.get("aggregate_sha256") != fresh_stats.get("aggregate_sha256"):
            problems.append(f"group digest mismatch: {group}")
    if manifest.get("aggregate_sha256") != fresh["aggregate_sha256"]:
        problems.append("aggregate digest mismatch")

    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1], help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Defaults to <root>/RELEASE_MANIFEST.json.",
    )
    args = parser.parse_args()

    manifest_path = args.manifest or (args.root / "RELEASE_MANIFEST.json")
    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found: {manifest_path}. Run scripts/make_release.py first.")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    problems = verify(args.root, manifest)
    if problems:
        print(f"Release verification FAILED with {len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        raise SystemExit(1)

    count = manifest.get("artifact_count", len(manifest.get("artifacts", [])))
    print(f"Release verification OK: {count} artifacts match the manifest exactly.")
    print(f"Aggregate: {manifest.get('aggregate_sha256')}")


if __name__ == "__main__":
    main()
