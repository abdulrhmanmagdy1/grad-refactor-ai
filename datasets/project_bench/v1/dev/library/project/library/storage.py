"""Saving and loading the catalog as JSON files in an export folder."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from library.catalog import Catalog
from library.models import Book


class ExportStore:
    """JSON exports of the catalog, kept in one folder."""

    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)

    def export_path(self, name: str) -> Path:
        """The file for an export called `name`, inside the export folder."""
        return self.folder / f"{name}.json"

    def save(self, catalog: Catalog, name: str) -> str:
        """Write the catalog and return the checksum of what was written."""
        self.folder.mkdir(parents=True, exist_ok=True)
        data = json.dumps([asdict(book) for book in catalog.books.values()], sort_keys=True)
        self.export_path(name).write_text(data, encoding="utf-8")
        return checksum(data.encode("utf-8"))

    def load(self, name: str) -> Catalog:
        """Read an export back into a new catalog."""
        catalog = Catalog()
        rows = json.loads(self.export_path(name).read_text(encoding="utf-8"))
        for row in rows:
            catalog.add(Book(**row))
        return catalog


def checksum(data: bytes) -> str:
    """A short fingerprint to tell two exports apart."""
    return hashlib.md5(data, usedforsecurity=False).hexdigest()
