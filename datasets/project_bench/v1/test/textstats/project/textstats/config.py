"""Settings for a textstats run, read from an INI or a JSON file."""

from __future__ import annotations

import configparser
import json
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from textstats.report import REPORT_COLUMNS

SECTION = "textstats"
INT_KEYS = ("min_word_length", "ngram_size", "top_words", "min_count")
LIST_KEYS = ("stopwords", "suffixes", "columns")


@dataclass(frozen=True)
class Settings:
    """Options for tokenizing, counting and choosing the report columns."""

    lowercase: bool = True
    min_word_length: int = 1
    ngram_size: int = 2
    top_words: int = 5
    min_count: int = 1
    stopwords: frozenset[str] = frozenset()
    suffixes: tuple[str, ...] = (".txt",)
    columns: tuple[str, ...] = REPORT_COLUMNS


def load_settings(path: Path) -> Settings:
    """Read settings from ``path``; the suffix (.ini, .cfg or .json) picks the format.

    Missing keys keep their default. Unknown keys, values of the wrong type and
    unknown report columns raise ValueError.
    """
    suffix = path.suffix.lower()
    if suffix in {".ini", ".cfg"}:
        raw = _read_ini(path)
    elif suffix == ".json":
        raw = _read_json(path)
    else:
        raise ValueError(f"unsupported settings file: {path.name}")
    return _build(raw)


def _read_ini(path: Path) -> dict[str, Any]:
    """Read the [textstats] section and convert its strings to typed values."""
    parser = configparser.ConfigParser()
    parser.read_string(path.read_text(encoding="utf-8"), source=str(path))
    if not parser.has_section(SECTION):
        raise ValueError(f"{path.name} has no [{SECTION}] section")
    section = parser[SECTION]
    raw: dict[str, Any] = dict(section)
    for key in LIST_KEYS:
        if key in raw:
            raw[key] = [item.strip() for item in raw[key].split(",") if item.strip()]
    for key in INT_KEYS:
        if key in raw:
            raw[key] = section.getint(key)
    if "lowercase" in raw:
        raw["lowercase"] = section.getboolean("lowercase")
    return raw


def _read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object of settings."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return data


def _build(raw: dict[str, Any]) -> Settings:
    """Validate the raw values and turn them into a Settings object."""
    unknown = set(raw) - {item.name for item in fields(Settings)}
    if unknown:
        raise ValueError(f"unknown setting(s): {', '.join(sorted(unknown))}")
    _check_scalars(raw)
    values = dict(raw)
    _normalize_lists(values)
    return Settings(**values)


def _check_scalars(raw: dict[str, Any]) -> None:
    """Raise ValueError unless the counts are positive integers and lowercase a bool."""
    for key in INT_KEYS:
        value = raw.get(key, 1)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{key} must be a positive whole number")
    if not isinstance(raw.get("lowercase", True), bool):
        raise ValueError("lowercase must be true or false")


def _normalize_lists(values: dict[str, Any]) -> None:
    """Convert the list settings, in place, to the types Settings expects."""
    if "stopwords" in values:
        values["stopwords"] = frozenset(word.lower() for word in values["stopwords"])
    if "suffixes" in values:
        values["suffixes"] = tuple(suffix.lower() for suffix in values["suffixes"])
    if "columns" in values:
        values["columns"] = _check_columns(values["columns"])


def _check_columns(columns: list[str]) -> tuple[str, ...]:
    """Return ``columns`` as a tuple after checking every name is a report column."""
    unknown = [name for name in columns if name not in REPORT_COLUMNS]
    if unknown:
        raise ValueError(f"unknown report column(s): {', '.join(unknown)}")
    if not columns:
        raise ValueError("the report needs at least one column")
    return tuple(columns)
