"""Reading the documents of a corpus folder."""

from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Document:
    """A text document: its name relative to the corpus folder, and its text."""

    name: str
    text: str


def read_text(path: Path) -> str:
    """Return the text of ``path``, decoded as UTF-8 or, failing that, Windows-1252."""
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252")


def load_document(root: Path, name: str) -> Document:
    """Load the document ``name`` from the corpus folder ``root``.

    ``name`` is the document's path relative to ``root`` as written in the corpus
    index; it may include subfolders, for example ``letters/1854.txt``.
    """
    path = root / name
    return Document(name=name, text=read_text(path))


def load_index(root: Path, index_name: str = "index.txt") -> list[Document]:
    """Load the documents listed in ``root / index_name``, one name per line.

    Blank lines and lines starting with '#' are ignored.
    """
    names = [line.strip() for line in read_text(root / index_name).splitlines()]
    return [load_document(root, name) for name in names if name and not name.startswith("#")]


def iter_documents(root: Path, suffixes: Iterable[str] = (".txt",)) -> Iterator[Document]:
    """Yield every non-empty document under ``root`` whose suffix is in ``suffixes``.

    Hidden files and folders (names starting with '.') are skipped, folders and files
    are visited in sorted order, and files that cannot be decoded are logged and
    skipped.
    """
    wanted = {suffix.lower() for suffix in suffixes}
    for folder, subfolders, filenames in os.walk(root):
        subfolders[:] = sorted(name for name in subfolders if not name.startswith("."))
        for filename in sorted(filenames):
            if not filename.startswith(".") and Path(filename).suffix.lower() in wanted:
                path = Path(folder) / filename
                try:
                    text = read_text(path)
                except UnicodeDecodeError:
                    logger.warning("skipping %s: unknown text encoding", path)
                else:
                    if text.strip():
                        name = path.relative_to(root).as_posix()
                        yield Document(name=name, text=text)


def fingerprint(text: str) -> str:
    """Checksum of ``text`` ignoring case and spacing, used to spot repeated documents."""
    normalized = " ".join(text.lower().split())
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()
