import pytest

from warehouse.models import Product
from warehouse.reports import low_stock, stock_csv, stock_value, summary
from warehouse.stock import StockLedger
from warehouse.storage import Movement, MovementLog

BOLT = Product("BOLT-10", "M10 bolt", 0.12, 0.02, reorder_point=50, reorder_quantity=500)
NUT = Product("NUT-10", "M10 nut", 0.05, 0.01, reorder_point=80, reorder_quantity=1000)


def make_ledger() -> StockLedger:
    ledger = StockLedger()
    ledger.receive("BOLT-10", "A1", 200)
    ledger.receive("NUT-10", "A1", 100)
    ledger.reserve("NUT-10", 30)
    return ledger


def test_stock_value_uses_units_on_hand() -> None:
    assert stock_value([BOLT, NUT], make_ledger()) == 29.00


def test_low_stock_lists_products_to_reorder() -> None:
    assert low_stock([NUT, BOLT], make_ledger()) == [NUT]


def test_stock_csv_rows() -> None:
    assert stock_csv([NUT, BOLT], make_ledger()).splitlines() == [
        "sku,name,on_hand,reserved,available",
        "BOLT-10,M10 bolt,200,0,200",
        "NUT-10,M10 nut,100,30,70",
    ]


def test_summary_text() -> None:
    assert summary([BOLT, NUT], make_ledger()) == "SKUs: 2\nStock value: 29.00\nReorder: NUT-10"


def test_movement_history_and_net_change() -> None:
    log = MovementLog()
    log.record(Movement("2026-03-01T08:00", "BOLT-10", "A1", 200, "receipt"))
    log.record(Movement("2026-03-02T09:30", "NUT-10", "A1", 100, "receipt"))
    log.record(Movement("2026-03-03T14:10", "BOLT-10", "A1", -40, "pick SO-1"))
    assert [m.quantity for m in log.history("BOLT-10")] == [200, -40]
    assert log.net_change("BOLT-10", "A1") == 160
    assert log.net_change("BOLT-10", "Z9") == 0
    log.close()


def test_latest_movements_sorted_by_column() -> None:
    log = MovementLog()
    log.record(Movement("2026-03-01T08:00", "BOLT-10", "A1", 200, "receipt"))
    log.record(Movement("2026-03-02T09:30", "NUT-10", "A1", 100, "receipt"))
    assert [m.sku for m in log.latest(limit=1)] == ["NUT-10"]
    assert [m.quantity for m in log.latest(order_by="quantity")] == [200, 100]
    with pytest.raises(ValueError):
        log.latest(order_by="reason")
    log.close()
