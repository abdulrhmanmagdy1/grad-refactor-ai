"""Runs one pipeline job: import, validate, clean, summarize, cache and export."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pipeline.aggregate import GroupSummary, summarize
from pipeline.cache import DiskCache, file_fingerprint, make_key
from pipeline.cleaning import clean_rows
from pipeline.export import open_database, write_summaries
from pipeline.importer import read_csv
from pipeline.validation import RowError, validate_rows

PIPELINE_VERSION = "3"


@dataclass(frozen=True)
class PipelineConfig:
    """One pipeline job.

    ``dataset`` is the name the job was submitted under; it names the cache
    entry and the rows in the export database. ``group_by``, ``value_column``
    and ``required`` are header names after normalization (lower-case, words
    joined by underscores).
    """

    source: Path
    dataset: str
    group_by: str
    value_column: str
    required: tuple[str, ...] = ()
    cache_dir: Path | None = None


@dataclass
class PipelineResult:
    summaries: list[GroupSummary]
    errors: list[RowError]
    from_cache: bool = False


def run_pipeline(config: PipelineConfig) -> PipelineResult:
    """Summarize one CSV file, reusing the cached result for an unchanged file.

    Rows with problems are left out of the summaries and reported in
    ``errors``. Without a ``cache_dir`` nothing is cached.
    """
    if config.cache_dir is None:
        return _compute(config)
    cache = DiskCache(config.cache_dir)
    key = make_key(
        config.dataset,
        file_fingerprint(config.source),
        config.group_by,
        config.value_column,
        *config.required,
    )
    stored = cache.get(key)
    if stored is not None:
        return _from_document(stored)
    result = _compute(config)
    cache.put(key, _to_document(result))
    return result


def _compute(config: PipelineConfig) -> PipelineResult:
    rows = read_csv(config.source)
    columns = (*config.required, config.group_by, config.value_column)
    required = tuple(dict.fromkeys(columns))
    valid, errors = validate_rows(rows, required, numeric=(config.value_column,))
    cleaned = clean_rows(
        valid, amount_columns=(config.value_column,), label_columns=(config.group_by,)
    )
    return PipelineResult(summarize(cleaned, config.group_by, config.value_column), errors)


def _to_document(result: PipelineResult) -> dict[str, Any]:
    return {
        "summaries": [asdict(summary) for summary in result.summaries],
        "errors": [asdict(error) for error in result.errors],
    }


def _from_document(document: dict[str, Any]) -> PipelineResult:
    return PipelineResult(
        summaries=[GroupSummary(**item) for item in document["summaries"]],
        errors=[RowError(**item) for item in document["errors"]],
        from_cache=True,
    )


def export(
    result: PipelineResult, dataset: str, connection: sqlite3.Connection | None = None
) -> sqlite3.Connection:
    """Write a result's summaries to the export database (a new in-memory one by default)."""
    if connection is None:
        connection = open_database()
    write_summaries(connection, dataset, result.summaries)
    return connection
