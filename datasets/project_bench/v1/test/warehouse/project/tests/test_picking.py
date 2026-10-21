import pytest

from warehouse.models import CustomerLine, PickTask
from warehouse.picking import WaveBuilder, confirm_picks, plan_picks
from warehouse.stock import InsufficientStock, StockLedger


def make_ledger() -> StockLedger:
    ledger = StockLedger()
    ledger.receive("BOLT-10", "C3", 10)
    ledger.receive("BOLT-10", "A1", 2)
    ledger.receive("NUT-10", "B2", 50)
    return ledger


def test_smallest_bin_is_picked_first() -> None:
    tasks = plan_picks(make_ledger(), [CustomerLine("SO-1", "BOLT-10", 5)])
    assert tasks == [
        PickTask("SO-1", "BOLT-10", "A1", 2),
        PickTask("SO-1", "BOLT-10", "C3", 3),
    ]


def test_units_are_not_planned_twice() -> None:
    lines = [CustomerLine("SO-1", "BOLT-10", 2), CustomerLine("SO-2", "BOLT-10", 4)]
    tasks = plan_picks(make_ledger(), lines)
    assert tasks == [
        PickTask("SO-1", "BOLT-10", "A1", 2),
        PickTask("SO-2", "BOLT-10", "C3", 4),
    ]


def test_plan_picks_refuses_lines_the_bins_cannot_cover() -> None:
    with pytest.raises(InsufficientStock):
        plan_picks(make_ledger(), [CustomerLine("SO-1", "BOLT-10", 13)])


def test_confirm_picks_moves_stock_and_reservations() -> None:
    ledger = make_ledger()
    ledger.reserve("NUT-10", 20)
    picked = confirm_picks(ledger, [PickTask("SO-3", "NUT-10", "B2", 20)])
    assert picked == 20
    assert ledger.on_hand("NUT-10") == 30
    assert ledger.reserved("NUT-10") == 0


def test_wave_is_limited_to_max_orders() -> None:
    wave = WaveBuilder(max_orders=2)
    assert wave.add(CustomerLine("SO-1", "BOLT-10", 1))
    assert wave.add(CustomerLine("SO-2", "NUT-10", 4))
    assert wave.add(CustomerLine("SO-1", "NUT-10", 2))
    assert not wave.add(CustomerLine("SO-3", "BOLT-10", 1))
    assert wave.order_count() == 2


def test_release_returns_the_wave_lines_in_order() -> None:
    wave = WaveBuilder(max_orders=3)
    first = CustomerLine("SO-1", "BOLT-10", 1)
    second = CustomerLine("SO-2", "NUT-10", 4)
    wave.add(first)
    wave.add(second)
    assert wave.release() == [first, second]
