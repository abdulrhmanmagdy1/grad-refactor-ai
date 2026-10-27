from datetime import date, datetime
from decimal import Decimal

import pytest

from pharmacy.controlled import ApprovalRegister
from pharmacy.dispensing import ApprovalRequired, Counter
from pharmacy.inventory import Inventory
from pharmacy.models import Batch, Medicine, Prescription, Role, Staff
from pharmacy.prescriptions import PrescriptionBook
from pharmacy.receipts import ReceiptBook, render

TODAY = date(2026, 3, 1)
PHARMACIST = Staff("S1", "Huda", Role.PHARMACIST)
CASHIER = Staff("S3", "Omar", Role.CASHIER)


def make_counter() -> Counter:
    stock = Inventory()
    stock.add_medicine(Medicine("PCM500", "Paracetamol", 500, Decimal("0.050"), 1000, 4000))
    stock.add_medicine(Medicine("MOR10", "Morphine", 10, Decimal("1.200"), 20, 120, True))
    stock.receive(Batch("PCM500", "P1", date(2027, 6, 30), 100))
    stock.receive(Batch("MOR10", "M1", date(2027, 6, 30), 50))
    book = PrescriptionBook()
    book.add(Prescription("RX1", "Salma", "PCM500", 500, 3, 20, date(2026, 2, 20)))
    book.add(Prescription("RX2", "Nasser", "MOR10", 10, 4, 28, date(2026, 2, 20)))
    return Counter(stock, book, ApprovalRegister(), ReceiptBook())


def test_fill_prescription_writes_receipt():
    counter = make_counter()
    receipt = counter.fill_prescription("RX1", CASHIER, TODAY)
    assert receipt.number == "R000001"
    assert receipt.subtotal == Decimal("1.00")
    assert receipt.vat == Decimal("0.05")
    assert receipt.total == Decimal("1.05")
    assert counter.stock.on_hand("PCM500", TODAY) == 80


def test_controlled_needs_approval_first():
    counter = make_counter()
    with pytest.raises(ApprovalRequired):
        counter.fill_prescription("RX2", PHARMACIST, TODAY)
    assert counter.approvals.pending() == [("RX2", 1)]
    assert counter.stock.on_hand("MOR10", TODAY) == 50
    counter.approvals.approve("RX2", 1, PHARMACIST, datetime(2026, 3, 1, 9, 30))
    receipt = counter.fill_prescription("RX2", PHARMACIST, TODAY)
    assert receipt.lines[0].quantity == 28
    assert counter.approvals.register_entries()[0].approved_by == "S1"


def test_controlled_not_sold_over_counter():
    counter = make_counter()
    with pytest.raises(ApprovalRequired):
        counter.sell_over_counter("MOR10", 1, CASHIER, TODAY)


def test_render_receipt():
    counter = make_counter()
    receipt = counter.sell_over_counter("PCM500", 10, CASHIER, TODAY)
    text = render(receipt, counter.stock)
    assert "10 x Paracetamol 500 mg  0.50 OMR" in text
    assert "lot P1" in text
    assert "SHORT-DATED" not in text
    assert text.endswith("Total 0.53 OMR")
