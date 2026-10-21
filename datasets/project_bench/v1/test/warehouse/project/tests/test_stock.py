import pytest

from warehouse.stock import InsufficientStock, StockLedger


def make_ledger() -> StockLedger:
    ledger = StockLedger()
    ledger.receive("BOLT-10", "A1", 40)
    ledger.receive("BOLT-10", "B2", 15)
    ledger.receive("NUT-10", "A1", 100)
    return ledger


def test_on_hand_adds_up_all_bins() -> None:
    ledger = make_ledger()
    assert ledger.on_hand("BOLT-10") == 55
    assert ledger.on_hand("NUT-10") == 100
    assert ledger.on_hand("WASHER-6") == 0


def test_remove_takes_units_out_of_one_bin() -> None:
    ledger = make_ledger()
    ledger.remove("BOLT-10", "A1", 30)
    assert ledger.bins_for("BOLT-10") == {"A1": 10, "B2": 15}


def test_remove_more_than_the_bin_holds_is_refused() -> None:
    ledger = make_ledger()
    with pytest.raises(InsufficientStock):
        ledger.remove("BOLT-10", "B2", 16)
    assert ledger.on_hand("BOLT-10") == 55


def test_receive_rejects_non_positive_quantities() -> None:
    ledger = StockLedger()
    with pytest.raises(ValueError, match="positive"):
        ledger.receive("BOLT-10", "A1", 0)


def test_reservations_reduce_what_is_available() -> None:
    ledger = make_ledger()
    ledger.reserve("BOLT-10", 50)
    assert ledger.available("BOLT-10") == 5
    with pytest.raises(InsufficientStock):
        ledger.reserve("BOLT-10", 6)


def test_release_never_goes_below_zero() -> None:
    ledger = make_ledger()
    ledger.reserve("NUT-10", 10)
    ledger.release("NUT-10", 25)
    assert ledger.reserved("NUT-10") == 0
    assert ledger.available("NUT-10") == 100


def test_skus_lists_what_is_in_stock() -> None:
    ledger = make_ledger()
    ledger.remove("NUT-10", "A1", 100)
    assert ledger.skus() == ["BOLT-10"]
