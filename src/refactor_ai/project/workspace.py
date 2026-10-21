"""Safe intake of an uploaded project zip into a workspace folder.

Only regular files with an allowed suffix are extracted, outside tool and environment
folders. Entries with absolute paths, drive letters, "..", links or names that would land
outside the workspace are refused, and every size limit is checked before a byte is
written. Nothing in the project is imported or executed here.
"""

from __future__ import annotations

import io
import stat
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

MAX_ZIP_BYTES = 5_000_000
MAX_ENTRIES = 5_000
MAX_PYTHON_FILES = 200
MAX_PYTHON_BYTES = 1_500_000
MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 8_000_000
ALLOWED_SUFFIXES = frozenset({".py", ".toml", ".cfg", ".ini", ".txt", ".md"})
SKIPPED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        ".env",
        "node_modules",
        "build",
        "dist",
        ".tox",
        ".nox",
        ".eggs",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "site-packages",
        ".idea",
        ".vscode",
    }
)


class IntakeError(ValueError):
    """The upload cannot be used; `code` is stable and `message` is for people."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Workspace:
    """The extracted project: `root` holds the files under their relative paths."""

    root: Path
    files: list[str] = field(default_factory=list)
    python_files: list[str] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    python_bytes: int = 0

    def path(self, relative: str) -> Path:
        return self.root / relative

    def read(self, relative: str) -> str:
        return self.path(relative).read_text(encoding="utf-8", errors="replace")


def _entry_path(name: str) -> PurePosixPath:
    """The normalized relative path of a zip entry; raises IntakeError if it is unsafe."""
    cleaned = name.replace("\\", "/")
    if cleaned.startswith("/") or (len(cleaned) > 1 and cleaned[1] == ":"):
        raise IntakeError("unsafe_entry", f"The zip contains an absolute path: {name!r}.")
    parts = [part for part in cleaned.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise IntakeError("unsafe_entry", f"The zip contains a path with '..': {name!r}.")
    if not parts:
        raise IntakeError("unsafe_entry", f"The zip contains an empty path: {name!r}.")
    return PurePosixPath(*parts)


def _is_link(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode)


def extract_project(data: bytes, destination: Path) -> Workspace:
    """Check the zip and extract the allowed files into `destination` (created)."""
    if len(data) > MAX_ZIP_BYTES:
        raise IntakeError(
            "too_large", f"The zip is {len(data):,} bytes; the limit is {MAX_ZIP_BYTES:,}."
        )
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise IntakeError("not_a_zip", "The upload is not a valid zip file.") from exc
    with archive:
        entries = archive.infolist()
        if len(entries) > MAX_ENTRIES:
            raise IntakeError(
                "too_many_files",
                f"The zip has {len(entries):,} entries; the limit is {MAX_ENTRIES:,}.",
            )
        selected: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
        skipped: list[dict] = []
        for info in entries:
            if info.is_dir():
                continue
            path = _entry_path(info.filename)
            if _is_link(info):
                raise IntakeError("unsafe_entry", f"The zip contains a link: {info.filename!r}.")
            if info.flag_bits & 0x1:
                raise IntakeError("unsafe_entry", f"The zip entry is encrypted: {info.filename!r}.")
            if any(
                part in SKIPPED_DIRECTORIES or part.endswith(".egg-info") for part in path.parts
            ):
                continue
            if path.suffix.lower() not in ALLOWED_SUFFIXES:
                skipped.append({"path": str(path), "reason": "file type is not reviewed"})
                continue
            if info.file_size > MAX_FILE_BYTES:
                skipped.append({"path": str(path), "reason": "file is larger than 1 MB"})
                continue
            selected.append((info, path))
        python = [(info, path) for info, path in selected if path.suffix.lower() == ".py"]
        if not python:
            raise IntakeError("no_python_files", "The zip contains no Python files to review.")
        if len(python) > MAX_PYTHON_FILES:
            raise IntakeError(
                "too_many_files",
                f"The project has {len(python)} Python files; the limit is {MAX_PYTHON_FILES}.",
            )
        python_bytes = sum(info.file_size for info, _ in python)
        if python_bytes > MAX_PYTHON_BYTES:
            raise IntakeError(
                "too_large",
                f"The Python files hold {python_bytes:,} bytes; the limit is {MAX_PYTHON_BYTES:,}.",
            )
        if sum(info.file_size for info, _ in selected) > MAX_TOTAL_BYTES:
            raise IntakeError("too_large", "The extracted files would exceed 8 MB.")
        destination.mkdir(parents=True, exist_ok=False)
        root = destination.resolve()
        workspace = Workspace(root=root, skipped=skipped, python_bytes=python_bytes)
        seen: set[str] = set()
        for info, path in selected:
            relative = path
            key = relative.as_posix()
            if key.lower() in seen:
                raise IntakeError("unsafe_entry", f"The zip contains {key!r} twice.")
            seen.add(key.lower())
            target = (root / key).resolve()
            if not target.is_relative_to(root):
                raise IntakeError(
                    "unsafe_entry", f"The zip entry {info.filename!r} leaves the project."
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source:
                content = source.read(MAX_FILE_BYTES + 1)
            if len(content) > MAX_FILE_BYTES:  # the header understated the size
                raise IntakeError("too_large", f"{key!r} is larger than its zip header says.")
            target.write_bytes(content)
            workspace.files.append(key)
            if relative.suffix.lower() == ".py":
                workspace.python_files.append(key)
        workspace.files.sort()
        workspace.python_files.sort()
        return workspace


def open_workspace(root: Path) -> Workspace:
    """A workspace object for a folder that `extract_project` wrote earlier."""
    root = root.resolve()
    files = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in ALLOWED_SUFFIXES
    )
    python = [name for name in files if name.endswith(".py")]
    size = sum((root / name).stat().st_size for name in python)
    return Workspace(root=root, files=files, python_files=python, python_bytes=size)
