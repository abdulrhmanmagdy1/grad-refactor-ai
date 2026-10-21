from pipeline.validation import RowError, is_missing, row_problems, validate_rows

ROWS = [
    {"region": "North", "amount": "10"},
    {"region": "", "amount": "5"},
    {"region": "South", "amount": "ten"},
    {"region": "East", "amount": "2.50"},
]


def test_is_missing():
    assert is_missing(None)
    assert is_missing("")
    assert is_missing("   ")
    assert not is_missing("0")
    assert not is_missing("North")


def test_row_problems():
    problems = row_problems(7, {"region": "", "amount": "x"}, ["region"], ["amount"])
    assert problems == [
        RowError(7, "region", "missing value"),
        RowError(7, "amount", "not a number: 'x'"),
    ]


def test_optional_numeric_column_may_be_empty():
    assert row_problems(0, {"amount": ""}, [], ["amount"]) == []


def test_valid_rows_keep_their_order():
    valid, _ = validate_rows(ROWS, required=["region", "amount"], numeric=["amount"])
    assert [row["region"] for row in valid] == ["North", "East"]


def test_problems_from_several_files_can_share_one_list():
    collected: list[RowError] = []
    validate_rows(ROWS, ["region", "amount"], ["amount"], collected)
    _, returned = validate_rows(ROWS[:2], ["region", "amount"], ["amount"], collected)
    assert returned is collected
    assert [(e.row, e.column) for e in collected] == [
        (1, "region"),
        (2, "amount"),
        (1, "region"),
    ]
