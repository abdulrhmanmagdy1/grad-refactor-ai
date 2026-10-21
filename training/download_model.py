"""Download a pinned model snapshot into models/<name>/ and verify it.

Run with the training environment from the repository root, for example:

    .venv-train/Scripts/python.exe training/download_model.py \
        --repo-id Qwen/Qwen2.5-Coder-0.5B-Instruct \
        --revision ea3f2471cf1b1f0db85067f1ef93848e38e88c25 \
        --local-dir models/Qwen2.5-Coder-0.5B-Instruct

For a repository with several quantizations, --include limits the download to matching
files, for example:

    .venv-train/Scripts/python.exe training/download_model.py \
        --repo-id Qwen/Qwen2.5-Coder-3B-Instruct-GGUF \
        --revision f74adce6aa16316c625447af059dbebe4983757c \
        --local-dir models/Qwen2.5-Coder-3B-Instruct-GGUF \
        --include "*q4_k_m.gguf" --include LICENSE

The revision must be an exact 40-character commit. Files are written straight into
--local-dir (huggingface_hub keeps only small metadata under <local-dir>/.cache), Xet
downloads are disabled so no second chunk-cache copy is created, and every file whose
repository entry is stored with LFS is checked against its published SHA-256. The
manifest (sizes, checksums, timings) is printed as JSON and written next to the files.
"""

from __future__ import annotations

import os

# Must be set before huggingface_hub is imported: plain HTTP downloads, no Xet cache copy.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import argparse  # noqa: E402
import fnmatch  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import time  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from pathlib import Path  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--revision", required=True, help="exact 40-character commit SHA")
    parser.add_argument("--local-dir", required=True, type=Path)
    parser.add_argument(
        "--min-free-gb",
        type=float,
        default=1.5,
        help="refuse to start if free disk after the download would drop below this",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=None,
        help="download only files matching this glob (repeatable); default: every file",
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        raise SystemExit("--revision must be an exact 40-character commit SHA, not a branch")

    from huggingface_hub import HfApi, __version__, snapshot_download

    info = HfApi().model_info(args.repo_id, revision=args.revision, files_metadata=True)
    if info.sha != args.revision:
        raise SystemExit(f"the hub resolved {args.revision} to {info.sha}")
    expected = {
        s.rfilename: s
        for s in info.siblings
        if args.include is None or any(fnmatch.fnmatch(s.rfilename, p) for p in args.include)
    }
    if not expected:
        raise SystemExit("no repository file matches --include")
    total = sum(s.size or 0 for s in expected.values())
    args.local_dir.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(args.local_dir).free
    if free - total < args.min_free_gb * 1e9:
        raise SystemExit(
            f"refusing to download {total / 1e9:.2f} GB with {free / 1e9:.2f} GB free; "
            f"at least {args.min_free_gb} GB must stay free"
        )
    started = time.perf_counter()
    snapshot_download(
        args.repo_id,
        revision=args.revision,
        local_dir=args.local_dir,
        allow_patterns=args.include,
    )
    elapsed = time.perf_counter() - started

    files = {}
    for name, sibling in sorted(expected.items()):
        path = args.local_dir / name
        if not path.is_file():
            raise SystemExit(f"missing file after download: {name}")
        size = path.stat().st_size
        if sibling.size is not None and size != sibling.size:
            raise SystemExit(f"size mismatch for {name}: {size} != {sibling.size}")
        digest = sha256_file(path)
        lfs_sha = sibling.lfs.sha256 if sibling.lfs else None
        if lfs_sha is not None and digest != lfs_sha:
            raise SystemExit(f"sha256 mismatch for {name}: {digest} != {lfs_sha}")
        files[name] = {"bytes": size, "sha256": digest, "lfs_sha256_verified": lfs_sha is not None}
    manifest = {
        "repo_id": args.repo_id,
        "revision": args.revision,
        "card_license": getattr(info.card_data, "license", None),
        "downloaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "download_seconds": round(elapsed, 1),
        "total_bytes": sum(item["bytes"] for item in files.values()),
        "huggingface_hub": __version__,
        "hf_hub_disable_xet": os.environ.get("HF_HUB_DISABLE_XET"),
        "files": files,
    }
    (args.local_dir / "download-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
