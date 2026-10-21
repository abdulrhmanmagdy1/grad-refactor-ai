"""CSV import: normalized headers, trimmed cells, blank lines skipped."""

from __future__ import annotations

import csv
import io
from pathlib import Path

Row = dict[str, str]


def normalize_header(name: str) -> str:
    """Trim a header cell, lower-case it and join its words with underscores."""
    return "_".join(name.strip().lower().split())


def read_csv(path: Path, delimiter: str = ",") -> list[Row]:
    """Read a CSV file whose first line is a header.

    Header names go through normalize_header and cells are trimmed. Lines that
    are completely blank are skipped, short rows are padded with "" and cells
    beyond the last header are ignored. A file without a header gives [].
    """
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        header = next(reader, None)
        if header is None:
            return []
        names = [normalize_header(cell) for cell in header]
        rows: list[Row] = []
        for record in reader:
            if not any(cell.strip() for cell in record):
                continue
            cells = [cell.strip() for cell in record]
            cells += [""] * (len(names) - len(cells))
            rows.append(dict(zip(names, cells, strict=False)))
        return rows


def read_csv_text(text: str, delimiter: str = ",") -> list[Row]:
    """Like read_csv, for CSV content that is already in memory (an upload)."""
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    header = next(reader, None)
    if header is None:
        return []
    names = [normalize_header(cell) for cell in header]
    rows: list[Row] = []
    for record in reader:
        if not any(cell.strip() for cell in record):
            continue
        cells = [cell.strip() for cell in record]
        cells += [""] * (len(names) - len(cells))
        rows.append(dict(zip(names, cells, strict=False)))
    return rows
