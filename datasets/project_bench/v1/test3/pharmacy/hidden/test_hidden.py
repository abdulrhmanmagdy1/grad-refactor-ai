from datetime import date, datetime
from decimal import Decimal

import pytest

from pharmacy.controlled import ApprovalRegister
from pharmacy.dispensing import ApprovalRequired, Counter
from pharmacy.inventory import Inventory, OutOfStock
from pharmacy.models import Batch, Medicine, Prescription, Role, Staff
from pharmacy.prescriptions import DosageError, PrescriptionBook, check_dosage
from pharmacy.receipts import ReceiptBook

TODAY = date(2026, 3, 1)
PHARMACIST = Staff("S1", "Huda", Role.PHARMACIST)
TECHNICIAN = Staff("S2", "Rami", Role.TECHNICIAN)
CASHIER = Staff("S3", "Omar", Role.CASHIER)
IBUPROFEN = Medicine("IBU400", "Ibuprofen", 400, Decimal("0.080"), 800, 2400)


def make_counter() -> Counter:
    stock = Inventory()
    stock.add_medicine(IBUPROFEN)
    stock.add_medicine(Medicine("MOR10", "Morphine", 10, Decimal("1.200"), 20, 120, True))
    stock.receive(Batch("IBU400", "I1", date(2027, 6, 30), 100))
    stock.receive(Batch("MOR10", "M1", date(2027, 6, 30), 50))
    book = PrescriptionBook()
    book.add(Prescription("RX1", "Salma", "IBU400", 400, 3, 20, date(2026, 2, 20), 1))
    book.add(Prescription("RX2", "Nasser", "MOR10", 10, 4, 28, date(2026, 2, 20)))
    return Counter(stock, book, ApprovalRegister(), ReceiptBook())


def requested(register: ApprovalRegister) -> ApprovalRegister:
    register.request("RX2", 1)
    return register


def test_B2_daily_total_above_limit_is_rejected():
    with pytest.raises(DosageError):
        check_dosage(IBUPROFEN, 800, 4)


def test_B3_take_uses_the_first_expiring_batch():
    stock = Inventory()
    stock.add_medicine(IBUPROFEN)
    stock.receive(Batch("IBU400", "LATE", date(2027, 12, 31), 10))
    stock.receive(Batch("IBU400", "EARLY", date(2026, 8, 31), 10))
    stock.receive(Batch("IBU400", "MIDDLE", date(2027, 3, 31), 10))
    picks = stock.take("IBU400", 14, TODAY)
    assert [(p.lot, p.quantity) for p in picks] == [("EARLY", 10), ("MIDDLE", 4)]


def test_S1_technician_cannot_approve_a_controlled_fill():
    register = requested(ApprovalRegister())
    with pytest.raises(PermissionError):
        register.approve("RX2", 1, TECHNICIAN, datetime(2026, 3, 1, 9, 0))
    assert not register.is_approved("RX2", 1)


def test_S1_cashier_cannot_approve_a_controlled_fill():
    register = requested(ApprovalRegister())
    with pytest.raises(PermissionError):
        register.approve("RX2", 1, CASHIER, datetime(2026, 3, 1, 9, 0))
    assert not register.is_approved("RX2", 1)


def test_keep_pharmacist_approval_lets_controlled_fill_through():
    counter = make_counter()
    with pytest.raises(ApprovalRequired):
        counter.fill_prescription("RX2", CASHIER, TODAY)
    counter.approvals.approve("RX2", 1, PHARMACIST, datetime(2026, 3, 1, 9, 0))
    receipt = counter.fill_prescription("RX2", CASHIER, TODAY)
    assert receipt.total == Decimal("35.28")


def test_keep_inactive_pharmacist_cannot_approve():
    register = requested(ApprovalRegister())
    off_duty = Staff("S9", "Laila", Role.PHARMACIST, active=False)
    with pytest.raises(PermissionError):
        register.approve("RX2", 1, off_duty, datetime(2026, 3, 1, 9, 0))


def test_keep_dose_at_the_daily_limit_is_allowed():
    assert check_dosage(IBUPROFEN, 800, 3) == 2400
    assert check_dosage(IBUPROFEN, 400, 6) == 2400


def test_keep_single_dose_limit():
    with pytest.raises(DosageError):
        check_dosage(IBUPROFEN, 1000, 1)


def test_keep_one_refill_means_two_fills():
    counter = make_counter()
    counter.fill_prescription("RX1", CASHIER, TODAY)
    counter.fill_prescription("RX1", CASHIER, date(2026, 3, 10))
    with pytest.raises(Exception):
        counter.fill_prescription("RX1", CASHIER, date(2026, 3, 20))
    assert counter.stock.on_hand("IBU400", TODAY) == 60


def test_keep_take_skips_expired_batches():
    stock = Inventory()
    stock.add_medicine(IBUPROFEN)
    stock.receive(Batch("IBU400", "OLD", date(2026, 2, 28), 10))
    stock.receive(Batch("IBU400", "GOOD", date(2026, 9, 30), 10))
    picks = stock.take("IBU400", 5, TODAY)
    assert [(p.lot, p.quantity) for p in picks] == [("GOOD", 5)]


def test_keep_failed_take_is_reported_to_the_caller():
    counter = make_counter()
    with pytest.raises(OutOfStock):
        counter.sell_over_counter("IBU400", 500, CASHIER, TODAY)
    assert counter.stock.on_hand("IBU400", TODAY) == 100
    assert counter.receipt_book.issued == []


def test_keep_remove_empty_drops_only_empty_batches():
    stock = Inventory()
    stock.add_medicine(IBUPROFEN)
    for lot in ("A", "B", "C", "D"):
        stock.receive(Batch("IBU400", lot, date(2027, 1, 1), 5))
    for batch in stock.sellable("IBU400", TODAY):
        if batch.lot in ("A", "B"):
            batch.quantity = 0
    assert stock.remove_empty() == 2
    assert sorted(b.lot for b in stock.sellable("IBU400", TODAY)) == ["C", "D"]


def test_keep_short_dated_sale_warns():
    counter = make_counter()
    counter.stock.receive(Batch("IBU400", "SOON", date(2026, 3, 15), 5))
    counter.sell_over_counter("IBU400", 105, CASHIER, TODAY)
    assert counter.warnings == ["Ibuprofen lot SOON is short-dated"]
    assert counter.stock.on_hand("IBU400", TODAY) == 0


def test_B1_expiry_report_is_the_same_when_asked_twice():
    stock = Inventory()
    stock.add_medicine(IBUPROFEN)
    stock.receive(Batch("IBU400", "SOON", date(2026, 3, 20), 3))
    first = list(stock.expiry_report(TODAY))
    second = stock.expiry_report(TODAY)
    assert len(first) == 1
    assert second == first
