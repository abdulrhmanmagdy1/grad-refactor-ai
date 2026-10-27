from datetime import date
from decimal import Decimal

import pytest

from pharmacy.models import Medicine, Prescription
from pharmacy.prescriptions import (
    DosageError,
    PrescriptionBook,
    PrescriptionError,
    check_dosage,
)

PARACETAMOL = Medicine("PCM500", "Paracetamol", 500, Decimal("0.050"), 1000, 4000)


def test_dose_within_limits_returns_daily_total():
    assert check_dosage(PARACETAMOL, 500, 3) == 1500


def test_single_dose_above_limit():
    with pytest.raises(DosageError):
        check_dosage(PARACETAMOL, 1500, 1)


def test_dose_must_be_positive():
    with pytest.raises(DosageError):
        check_dosage(PARACETAMOL, 0, 2)


def test_prescription_without_refills_fills_once():
    book = PrescriptionBook()
    book.add(Prescription("RX1", "Salma", "PCM500", 500, 3, 20, date(2026, 1, 10)))
    book.check_fillable("RX1", date(2026, 1, 10))
    book.record_fill("RX1", date(2026, 1, 10))
    with pytest.raises(PrescriptionError):
        book.check_fillable("RX1", date(2026, 1, 20))


def test_old_prescription_cannot_be_filled():
    book = PrescriptionBook()
    book.add(Prescription("RX2", "Salma", "PCM500", 500, 3, 20, date(2025, 1, 10), 5))
    with pytest.raises(PrescriptionError):
        book.check_fillable("RX2", date(2026, 1, 10))


def test_duplicate_id_rejected():
    book = PrescriptionBook()
    book.add(Prescription("RX3", "Ali", "PCM500", 500, 2, 10, date(2026, 1, 1)))
    with pytest.raises(ValueError):
        book.add(Prescription("RX3", "Ali", "PCM500", 500, 2, 10, date(2026, 1, 2)))


def test_for_patient_newest_first():
    book = PrescriptionBook()
    book.add(Prescription("A", "Ali", "PCM500", 500, 2, 10, date(2026, 1, 1)))
    book.add(Prescription("B", "Ali", "PCM500", 500, 2, 10, date(2026, 2, 1)))
    assert [rx.rx_id for rx in book.for_patient("Ali")] == ["B", "A"]
