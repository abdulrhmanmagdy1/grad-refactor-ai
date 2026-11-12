"""Report hardware and workspace readiness without sending anything anywhere.

Prints the OS/GPU facts recorded for experiment manifests, the local toolchain,
the state of the built web client, the SQLite database health and which release
artifacts are present on this machine. It is the first command to run when
checking a clean clone on the second machine (pair it with
``scripts/verify_release.py`` to prove the committed artifacts match
``RELEASE_MANIFEST.json``).

The report is JSON on stdout so it can be pasted into an issue or an experiment
record; nothing is transmitted anywhere.
"""

import json
import platform
import shutil
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

root = Path(__file__).resolve().parents[1]
dist = root / "frontend" / "dist"
entry = dist / "index.html"


def _tool(name: str, *version_args: str) -> dict:
    """Locate a tool and record its first version line."""
    executable = shutil.which(name)
    if not executable:
        return {"present": False}
    try:
        result = subprocess.run(
            [executable, *version_args],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        line = (result.stdout or result.stderr).strip().splitlines()
        version = line[0] if line else "unknown"
    except (OSError, subprocess.SubprocessError) as exc:  # noqa: BLE001 - doctor never raises
        version = f"unavailable: {exc}"
    return {"present": True, "version": version}


def _web_client() -> dict:
    """Describe the built bundle and whether it is older than its sources."""
    if not entry.exists():
        return {"built": False, "hint": "cd frontend && npm ci && npm run build"}
    built_at = datetime.fromtimestamp(entry.stat().st_mtime, tz=UTC).isoformat()
    sources = [
        path
        for pattern in ("src/**/*", "package.json", "vite.config.ts", "tsconfig*.json")
        for path in (root / "frontend").glob(pattern)
        if path.is_file()
    ]
    newest_source = max((path.stat().st_mtime for path in sources), default=0)
    return {
        "built": True,
        "built_at": built_at,
        "stale": newest_source > entry.stat().st_mtime,
        "hint": "rebuild with: cd frontend && npm run build",
    }


def _database() -> dict:
    """Run SQLite's own integrity check and count the stored runs."""
    path = root / "runs.sqlite3"
    if not path.exists():
        return {"present": False, "hint": "created on the first run"}
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            runs = connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        finally:
            connection.close()
    except sqlite3.Error as exc:
        return {"present": True, "error": str(exc)}
    return {"present": True, "integrity": integrity, "runs": runs}


info: dict = {
    "python": sys.version.split()[0],
    "os": platform.system(),
    "architecture": platform.machine(),
    "gpu": "not detected; confirm manually",
}
if shutil.which("nvidia-smi"):
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode == 0:
        info["gpu"] = result.stdout.strip()

info["tools"] = {
    "node": _tool("node", "--version"),
    "npm": _tool("npm", "--version"),
    "uv": _tool("uv", "--version"),
    "ffmpeg": _tool("ffmpeg", "-version"),
}
info["workspace"] = {
    "curated_dataset": (root / "data" / "curated.jsonl").exists(),
    "frontend_build": entry.exists(),
    "release_manifest": (root / "RELEASE_MANIFEST.json").exists(),
    "blind_review_packet": (root / "experiments" / "review" / "packet.md").exists(),
}
info["web_client"] = _web_client()
info["database"] = _database()
print(json.dumps(info, ensure_ascii=False, indent=2))
