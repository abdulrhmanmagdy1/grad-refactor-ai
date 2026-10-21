import csv

from pipeline.aggregate import GroupSummary
from pipeline.export import COLUMNS, open_database, read_summaries, write_csv, write_summaries

SUMMARIES = [
    GroupSummary("North", 3, 10.3, 10.3 / 3, 0.1, 10.0),
    GroupSummary("South", 2, 10.0, 5.0, 4.0, 6.0),
]


def test_sqlite_round_trip():
    connection = open_database()
    assert write_summaries(connection, "sales", SUMMARIES) == 2
    assert read_summaries(connection, "sales") == SUMMARIES
    assert read_summaries(connection, "other") == []


def test_writing_a_dataset_again_replaces_it():
    connection = open_database()
    write_summaries(connection, "sales", SUMMARIES)
    write_summaries(connection, "sales", SUMMARIES[:1])
    write_summaries(connection, "returns", SUMMARIES[1:])
    assert read_summaries(connection, "sales") == SUMMARIES[:1]
    assert read_summaries(connection, "returns") == SUMMARIES[1:]


def test_database_file(tmp_path):
    path = str(tmp_path / "export.db")
    write_summaries(open_database(path), "sales", SUMMARIES)
    assert read_summaries(open_database(path), "sales") == SUMMARIES


def test_write_csv(tmp_path):
    path = tmp_path / "out.csv"
    assert write_csv(path, SUMMARIES) == 2
    with path.open(newline="", encoding="utf-8") as handle:
        lines = list(csv.reader(handle))
    assert lines[0] == list(COLUMNS)
    assert lines[2] == ["South", "2", "10.00", "5.0", "4.0", "6.0"]
