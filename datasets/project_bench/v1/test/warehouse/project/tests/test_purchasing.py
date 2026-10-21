import pytest

from warehouse.models import Product
from warehouse.purchasing import (
    book_delivery,
    create_order,
    needs_reorder,
    receive_line,
    suggest_reorders,
)
from warehouse.stock import StockLedger

BOLT = Product("BOLT-10", "M10 bolt", 0.12, 0.02, reorder_point=50, reorder_quantity=500)
NUT = Product("NUT-10", "M10 nut", 0.05, 0.01, reorder_point=80, reorder_quantity=1000)


def test_create_order_has_one_line_per_sku_sorted() -> None:
    order = create_order("PO-1", "Fasteners Ltd", {"NUT-10": 1000, "BOLT-10": 500})
    assert [(line.sku, line.ordered, line.received) for line in order.lines] == [
        ("BOLT-10", 500, 0),
        ("NUT-10", 1000, 0),
    ]


def test_create_order_rejects_bad_quantities() -> None:
    with pytest.raises(ValueError, match="NUT-10"):
        create_order("PO-2", "Fasteners Ltd", {"BOLT-10": 5, "NUT-10": 0})
    with pytest.raises(ValueError):
        create_order("PO-3", "Fasteners Ltd", {})


def test_partial_deliveries_count_down_to_complete() -> None:
    order = create_order("PO-4", "Fasteners Ltd", {"BOLT-10": 10})
    assert receive_line(order, "BOLT-10", 4) == 6
    assert not order.is_complete
    assert receive_line(order, "BOLT-10", 6) == 0
    assert order.is_complete


def test_receive_line_for_unknown_sku() -> None:
    order = create_order("PO-5", "Fasteners Ltd", {"BOLT-10": 10})
    with pytest.raises(KeyError):
        receive_line(order, "NUT-10", 1)


def test_book_delivery_puts_goods_away() -> None:
    ledger = StockLedger()
    order = create_order("PO-6", "Fasteners Ltd", {"BOLT-10": 500, "NUT-10": 1000})
    completed = book_delivery(order, ledger, "R1", {"BOLT-10": 500, "NUT-10": 400})
    assert completed == ["BOLT-10"]
    assert ledger.bins_for("NUT-10") == {"R1": 400}


def test_needs_reorder_uses_available_stock() -> None:
    ledger = StockLedger()
    ledger.receive("BOLT-10", "A1", 70)
    assert not needs_reorder(BOLT, ledger)
    ledger.reserve("BOLT-10", 20)
    assert needs_reorder(BOLT, ledger)


def test_suggest_reorders_skips_skus_already_on_order() -> None:
    ledger = StockLedger()
    ledger.receive("BOLT-10", "A1", 10)
    ledger.receive("NUT-10", "A1", 10)
    open_order = create_order("PO-7", "Fasteners Ltd", {"NUT-10": 1000})
    assert suggest_reorders([BOLT, NUT], ledger, [open_order]) == {"BOLT-10": 500}
