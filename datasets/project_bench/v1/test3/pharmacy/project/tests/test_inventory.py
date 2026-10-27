from datetime import date
from decimal import Decimal

import pytest

from pharmacy.inventory import Inventory, OutOfStock, describe_pick
from pharmacy.models import Batch, Medicine

TODAY = date(2026, 3, 1)


def make_stock() -> Inventory:
    stock = Inventory()
    stock.add_medicine(Medicine("AMX500", "Amoxicillin", 500, Decimal("0.250"), 1000, 3000))
    return stock


def test_receive_rejects_unknown_medicine():
    stock = make_stock()
    with pytest.raises(KeyError):
        stock.receive(Batch("XYZ", "L1", date(2027, 1, 1), 10))


def test_receive_rejects_empty_batch():
    stock = make_stock()
    with pytest.raises(ValueError):
        stock.receive(Batch("AMX500", "L1", date(2027, 1, 1), 0))


def test_take_from_one_batch():
    stock = make_stock()
    stock.receive(Batch("AMX500", "L1", date(2027, 1, 1), 20))
    picks = stock.take("AMX500", 6, TODAY)
    assert [(p.lot, p.quantity) for p in picks] == [("L1", 6)]
    assert stock.on_hand("AMX500", TODAY) == 14


def test_take_more_than_on_hand_leaves_stock_alone():
    stock = make_stock()
    stock.receive(Batch("AMX500", "L1", date(2027, 1, 1), 5))
    with pytest.raises(OutOfStock):
        stock.take("AMX500", 6, TODAY)
    assert stock.on_hand("AMX500", TODAY) == 5


def test_batch_sells_on_its_expiry_day_but_not_after():
    stock = make_stock()
    stock.receive(Batch("AMX500", "L1", TODAY, 5))
    assert stock.on_hand("AMX500", TODAY) == 5
    assert stock.on_hand("AMX500", date(2026, 3, 2)) == 0


def test_remove_empty():
    stock = make_stock()
    stock.receive(Batch("AMX500", "L1", date(2027, 1, 1), 4))
    stock.take("AMX500", 4, TODAY)
    assert stock.remove_empty() == 1
    assert stock.sellable("AMX500", TODAY) == []


def test_expiry_report_lists_short_dated_batches():
    stock = make_stock()
    stock.receive(Batch("AMX500", "SOON", date(2026, 3, 20), 3))
    stock.receive(Batch("AMX500", "LATER", date(2026, 9, 1), 3))
    report = stock.expiry_report(TODAY)
    assert len(report) == 1
    assert "SOON" in report[0]


def test_stock_value_and_description():
    stock = make_stock()
    stock.receive(Batch("AMX500", "L1", date(2027, 1, 1), 10))
    assert stock.stock_value(TODAY) == "2.50 OMR"
    pick = stock.take("AMX500", 1, TODAY)[0]
    assert describe_pick(stock, pick) == "Amoxicillin 500 mg, lot L1, exp 2027-01-01"
