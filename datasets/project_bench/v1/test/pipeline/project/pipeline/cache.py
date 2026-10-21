"""A small on-disk cache of JSON documents, one file per key."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from pipeline import runner


def file_fingerprint(path: Path) -> str:
    """A checksum of a file's bytes, used to notice that a source file changed."""
    digest = hashlib.md5(usedforsecurity=False)
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_key(dataset: str, *settings: str) -> str:
    """The cache key for a dataset's result under the given settings.

    The settings are hashed together with the pipeline version, so a result
    is only reused for the same settings and the same version of the code.
    """
    joined = "\x1f".join([runner.PIPELINE_VERSION, *settings])
    return f"{dataset}-{hashlib.sha256(joined.encode('utf-8')).hexdigest()[:20]}"


class DiskCache:
    """JSON documents stored as ``<root>/<key>.json``."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> Any | None:
        """The stored document, or None when there is none or it is unreadable."""
        try:
            with self._path(key).open(encoding="utf-8") as handle:
                return json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def put(self, key: str, document: Any) -> None:
        """Store a JSON-serializable document, replacing an older one atomically."""
        path = self._path(key)
        partial = path.with_name(path.name + ".partial")
        with partial.open("w", encoding="utf-8") as handle:
            json.dump(document, handle, sort_keys=True)
        os.replace(partial, path)

    def clear(self) -> int:
        """Delete every stored document and return how many there were."""
        removed = 0
        for path in self.root.glob("*.json"):
            path.unlink()
            removed += 1
        return removed
