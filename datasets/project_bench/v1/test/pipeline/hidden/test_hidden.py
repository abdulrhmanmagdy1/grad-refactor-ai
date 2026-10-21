import sqlite3

import pytest

from pipeline import PipelineConfig, export, run_pipeline
from pipeline.aggregate import GroupSummary
from pipeline.cache import DiskCache, file_fingerprint
from pipeline.cleaning import parse_amount
from pipeline.export import open_database, read_summaries, write_summaries
from pipeline.validation import RowError, is_missing, validate_rows

CSV = "Region,Amount\nNorth,10\nSouth,4\nNorth,2.50\n"


def _files_outside(root, folder):
    return sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and folder not in p.parents
    )


# --- seeded issues -------------------------------------------------------------


def test_B1_validate_rows_starts_a_new_error_list_on_each_call():
    rows = [{"region": "North", "amount": "oops"}]
    _, first = validate_rows(rows, ["region", "amount"], ["amount"])
    _, second = validate_rows(rows, ["region", "amount"], ["amount"])
    assert first is not second
    assert second == [RowError(0, "amount", "not a number: 'oops'")]


def test_B2_amounts_round_half_cents_away_from_zero():
    assert parse_amount("0.125") == pytest.approx(0.13, abs=1e-9)
    assert parse_amount("$0.625") == pytest.approx(0.63, abs=1e-9)
    assert parse_amount("(0.625)") == pytest.approx(-0.63, abs=1e-9)


def test_B3_placeholders_are_missing_whatever_their_case():
    for text in ("NA", " N/A ", "Null", "NONE", "None"):
        assert is_missing(text), text


def test_S1_dataset_name_cannot_write_outside_the_cache_folder(tmp_path):
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    source = jobs / "sales.csv"
    source.write_text(CSV, encoding="utf-8")
    cache_dir = jobs / "cache"
    before = _files_outside(tmp_path, cache_dir)
    config = PipelineConfig(source, "../../escaped", "region", "amount", cache_dir=cache_dir)
    try:
        run_pipeline(config)
    except Exception:
        pass
    assert _files_outside(tmp_path, cache_dir) == before


# --- behaviour that must keep working -----------------------------------------


def test_keep_validate_rows_appends_to_a_given_list():
    collected = [RowError(9, "x", "earlier")]
    rows = [{"region": "", "amount": "1"}, {"region": "North", "amount": "2"}]
    valid, returned = validate_rows(rows, ["region", "amount"], ["amount"], collected)
    assert returned is collected
    assert collected == [RowError(9, "x", "earlier"), RowError(0, "region", "missing value")]
    assert valid == [{"region": "North", "amount": "2"}]


def test_keep_parse_amount_formats():
    assert parse_amount("1,234.50") == pytest.approx(1234.5)
    assert parse_amount("(3.10)") == pytest.approx(-3.1)
    assert parse_amount("-4") == pytest.approx(-4.0)
    assert parse_amount("2.999") == pytest.approx(3.0)
    assert parse_amount("0.124") == pytest.approx(0.12)
    assert parse_amount("€ 7.25") == pytest.approx(7.25)


def test_keep_parse_amount_rejects_non_numbers():
    for text in ("", "abc", "1.2.3", "nan", "inf"):
        with pytest.raises(ValueError):
            parse_amount(text)


def test_keep_is_missing_basics():
    assert is_missing(None)
    assert is_missing("")
    assert is_missing("  ")
    assert is_missing("n/a")
    assert not is_missing("0")
    assert not is_missing("North")
    assert not is_missing("Nadia")


def test_keep_cache_round_trip_for_ordinary_keys(tmp_path):
    cache = DiskCache(tmp_path / "cache")
    cache.put("sales_2024-0a1b2c", {"total": 1.5})
    assert cache.get("sales_2024-0a1b2c") == {"total": 1.5}
    assert cache.get("returns-0a1b2c") is None
    assert cache.clear() == 1


def test_keep_fingerprint_tracks_content(tmp_path):
    first = tmp_path / "a.csv"
    second = tmp_path / "b.csv"
    first.write_text(CSV, encoding="utf-8")
    second.write_text(CSV, encoding="utf-8")
    assert file_fingerprint(first) == file_fingerprint(second)
    second.write_text(CSV + "West,1\n", encoding="utf-8")
    assert file_fingerprint(first) != file_fingerprint(second)


def test_keep_export_stores_odd_names_verbatim():
    connection = open_database()
    dataset = "o'brien'); DROP TABLE group_summary; --"
    summaries = [GroupSummary("St. John's \"Main\"", 1, 2.0, 2.0, 2.0, 2.0)]
    write_summaries(connection, dataset, summaries)
    assert read_summaries(connection, dataset) == summaries
    tables = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    assert [row[0] for row in tables] == ["group_summary"]


def test_keep_pipeline_with_cache_and_export(tmp_path):
    source = tmp_path / "sales.csv"
    source.write_text(CSV, encoding="utf-8")
    config = PipelineConfig(source, "sales", "region", "amount", cache_dir=tmp_path / "cache")
    first = run_pipeline(config)
    second = run_pipeline(config)
    assert not first.from_cache
    assert second.from_cache
    assert [(s.key, s.count, s.total) for s in second.summaries] == [
        ("North", 2, 12.5),
        ("South", 1, 4.0),
    ]
    connection = export(second, "sales")
    assert isinstance(connection, sqlite3.Connection)
    assert read_summaries(connection, "sales") == second.summaries
