from pipeline.importer import normalize_header, read_csv, read_csv_text

SAMPLE = "Region , Unit Price,Qty\n north , 1.50 ,2\n\n , ,\nSouth,3\n"
EXPECTED = [
    {"region": "north", "unit_price": "1.50", "qty": "2"},
    {"region": "South", "unit_price": "3", "qty": ""},
]


def test_normalize_header():
    assert normalize_header("  Unit   Price ") == "unit_price"


def test_read_csv(tmp_path):
    path = tmp_path / "sales.csv"
    path.write_text(SAMPLE, encoding="utf-8")
    assert read_csv(path) == EXPECTED


def test_read_csv_handles_a_byte_order_mark(tmp_path):
    path = tmp_path / "sales.csv"
    path.write_bytes("﻿Region,Qty\nNorth,1\n".encode())
    assert read_csv(path) == [{"region": "North", "qty": "1"}]


def test_read_csv_ignores_extra_cells(tmp_path):
    path = tmp_path / "sales.csv"
    path.write_text("a,b\n1,2,3\n", encoding="utf-8")
    assert read_csv(path) == [{"a": "1", "b": "2"}]


def test_empty_file_gives_no_rows(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    assert read_csv(path) == []


def test_read_csv_text_matches_read_csv():
    assert read_csv_text(SAMPLE) == EXPECTED
    assert read_csv_text("a;b\n1;2\n", delimiter=";") == [{"a": "1", "b": "2"}]
