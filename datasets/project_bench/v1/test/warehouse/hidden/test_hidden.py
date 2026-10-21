import pytest

from warehouse.models import CustomerLine, Product
from warehouse.picking import WaveBuilder, plan_picks
from warehouse.purchasing import create_order, needs_reorder, receive_line
from warehouse.reports import low_stock
from warehouse.shipping import MAX_PARCEL_KG, billable_weight, pack_order, parcel_price
from warehouse.stock import StockLedger
from warehouse.storage import Movement, MovementLog


def _log_with_movements() -> MovementLog:
    log = MovementLog()
    log.record(Movement("2026-03-01T08:00", "BOLT-10", "A1", 200, "receipt"))
    log.record(Movement("2026-03-02T09:30", "NUT-10", "C3", 100, "receipt"))
    log.record(Movement("2026-03-03T14:10", "BOLT-10", "B2", -40, "pick SO-1"))
    return log


# --- seeded issues -------------------------------------------------------


def test_B1_delivery_cannot_take_a_line_past_what_was_ordered() -> None:
    order = create_order("PO-1", "Fasteners Ltd", {"BOLT-10": 10})
    receive_line(order, "BOLT-10", 6)
    with pytest.raises(ValueError):
        receive_line(order, "BOLT-10", 6)
    assert order.line_for("BOLT-10").received == 6


def test_B2_a_started_kilogram_is_billed_in_full() -> None:
    assert billable_weight(2.2) == 3
    assert billable_weight(4.01) == 5
    assert billable_weight(0.4) == 1
    assert parcel_price(2.2) == 6.90


def test_B3_a_released_wave_starts_empty() -> None:
    wave = WaveBuilder(max_orders=2)
    wave.add(CustomerLine("SO-1", "BOLT-10", 1))
    wave.add(CustomerLine("SO-2", "NUT-10", 1))
    wave.release()
    assert wave.add(CustomerLine("SO-3", "BOLT-10", 1))
    assert wave.add(CustomerLine("SO-4", "NUT-10", 1))
    assert not wave.add(CustomerLine("SO-5", "NUT-10", 1))
    assert [line.order_id for line in wave.release()] == ["SO-3", "SO-4"]


def test_S1_history_does_not_run_the_sku_as_sql() -> None:
    log = _log_with_movements()
    try:
        rows = log.history("NOPE' OR '1'='1")
    except ValueError:
        rows = []
    assert rows == []
    assert [m.quantity for m in log.history("BOLT-10")] == [200, -40]
    log.close()


# --- behaviour that must not change ---------------------------------------


def test_keep_delivery_may_complete_a_line_exactly() -> None:
    order = create_order("PO-2", "Fasteners Ltd", {"BOLT-10": 10, "NUT-10": 5})
    assert receive_line(order, "BOLT-10", 6) == 4
    assert receive_line(order, "BOLT-10", 4) == 0
    assert receive_line(order, "NUT-10", 5) == 0
    assert order.is_complete
    with pytest.raises(ValueError):
        receive_line(order, "NUT-10", 0)


def test_keep_whole_kilograms_are_billed_as_they_are() -> None:
    assert billable_weight(3.0) == 3
    assert billable_weight(1.0) == 1
    assert billable_weight(25.0) == 25
    assert parcel_price(25.0) == 15.00
    assert parcel_price(5.0) == 6.90
    with pytest.raises(ValueError):
        billable_weight(-1.0)


def test_keep_full_wave_refuses_new_orders_but_not_known_ones() -> None:
    wave = WaveBuilder(max_orders=1)
    assert wave.add(CustomerLine("SO-1", "BOLT-10", 1))
    assert not wave.add(CustomerLine("SO-2", "BOLT-10", 1))
    assert wave.add(CustomerLine("SO-1", "NUT-10", 3))
    assert [line.sku for line in wave.release()] == ["BOLT-10", "NUT-10"]


def test_keep_history_lists_one_sku_oldest_first() -> None:
    log = _log_with_movements()
    assert log.history("BOLT-10") == [
        Movement("2026-03-01T08:00", "BOLT-10", "A1", 200, "receipt"),
        Movement("2026-03-03T14:10", "BOLT-10", "B2", -40, "pick SO-1"),
    ]
    assert log.history("WASHER-6") == []
    log.close()


def test_keep_latest_sorts_only_by_known_columns() -> None:
    log = _log_with_movements()
    assert [m.bin_code for m in log.latest(order_by="bin_code")] == ["C3", "B2", "A1"]
    assert [m.quantity for m in log.latest(limit=2, order_by="quantity")] == [200, 100]
    with pytest.raises(ValueError):
        log.latest(order_by="quantity; DROP TABLE movements")
    assert log.net_change("BOLT-10", "A1") == 200
    log.close()


def test_keep_prune_empty_bins_forgets_only_empty_bins() -> None:
    ledger = StockLedger()
    ledger.receive("BOLT-10", "A1", 5)
    ledger.receive("NUT-10", "A1", 3)
    ledger.receive("BOLT-10", "B2", 4)
    ledger.receive("NUT-10", "C3", 2)
    ledger.remove("BOLT-10", "B2", 4)
    ledger.remove("NUT-10", "C3", 2)
    ledger.remove("NUT-10", "A1", 3)
    assert ledger.prune_empty_bins() == ["B2", "C3"]
    assert ledger.bins_for("BOLT-10") == {"A1": 5}
    assert ledger.skus() == ["BOLT-10"]
    assert ledger.prune_empty_bins() == []


def test_keep_pack_order_never_overfills_a_parcel() -> None:
    products = {
        "ANVIL-S": Product("ANVIL-S", "Small anvil", 40.0, 9.0, 2, 5),
        "TONGS-1": Product("TONGS-1", "Forge tongs", 12.0, 2.5, 5, 20),
        "FILE-8": Product("FILE-8", "Flat file", 6.0, 0.5, 5, 20),
    }
    quantities = {"ANVIL-S": 5, "TONGS-1": 7, "FILE-8": 9}
    parcels = pack_order("SO-12", quantities, products)
    assert all(parcel.weight_kg <= MAX_PARCEL_KG for parcel in parcels)
    for sku, quantity in quantities.items():
        assert sum(parcel.items.get(sku, 0) for parcel in parcels) == quantity
    assert len(parcels) == 3


def test_keep_low_stock_agrees_with_the_reorder_rule() -> None:
    products = [
        Product("BOLT-10", "M10 bolt", 0.12, 0.02, 50, 500),
        Product("NUT-10", "M10 nut", 0.05, 0.01, 80, 1000),
        Product("PIN-3", "Pin", 0.01, 0.01, 0, 100),
        Product("WASHER-6", "Washer", 0.02, 0.01, 10, 100),
    ]
    ledger = StockLedger()
    ledger.receive("BOLT-10", "A1", 51)
    ledger.receive("NUT-10", "A1", 100)
    ledger.reserve("NUT-10", 20)
    ledger.receive("PIN-3", "B2", 10)
    ledger.reserve("PIN-3", 10)
    ledger.remove("PIN-3", "B2", 4)
    expected = sorted(
        (product for product in products if needs_reorder(product, ledger)),
        key=lambda product: product.sku,
    )
    assert low_stock(products, ledger) == expected
    assert [product.sku for product in expected] == ["NUT-10", "PIN-3", "WASHER-6"]


def test_keep_plan_picks_empties_the_smallest_bin_first() -> None:
    ledger = StockLedger()
    ledger.receive("BOLT-10", "C3", 8)
    ledger.receive("BOLT-10", "A1", 8)
    ledger.receive("BOLT-10", "B2", 3)
    tasks = plan_picks(ledger, [CustomerLine("SO-1", "BOLT-10", 12)])
    assert [(task.bin_code, task.quantity) for task in tasks] == [("B2", 3), ("A1", 8), ("C3", 1)]
    assert ledger.on_hand("BOLT-10") == 19
