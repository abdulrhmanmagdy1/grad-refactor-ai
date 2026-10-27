"""The counter: filling prescriptions and over-the-counter sales."""

from __future__ import annotations

import logging
from datetime import date

from pharmacy.controlled import ApprovalRegister
from pharmacy.inventory import Inventory
from pharmacy.models import Medicine, Pick, Staff
from pharmacy.prescriptions import PrescriptionBook, check_dosage
from pharmacy.receipts import Receipt, ReceiptBook, ReceiptLine

logger = logging.getLogger(__name__)


class ApprovalRequired(Exception):
    """Raised when a controlled medicine is asked for before a pharmacist approved it."""


class Counter:
    """Fills prescriptions and sells medicines, keeping stock and records in step."""

    def __init__(
        self,
        stock: Inventory,
        prescriptions: PrescriptionBook,
        approvals: ApprovalRegister,
        receipt_book: ReceiptBook,
    ) -> None:
        self.stock = stock
        self.prescriptions = prescriptions
        self.approvals = approvals
        self.receipt_book = receipt_book
        self.warnings: list[str] = []

    def fill_prescription(self, rx_id: str, staff: Staff, on: date) -> Receipt:
        """Fill a prescription and return the receipt.

        The prescription must be fillable and its dose within the medicine's limits. A
        controlled medicine also needs a pharmacist's approval of this particular fill:
        without one, an approval is requested and ApprovalRequired is raised, and
        nothing is taken from stock.
        """
        prescription = self.prescriptions.check_fillable(rx_id, on)
        medicine = self.stock.medicine(prescription.medicine_code)
        check_dosage(medicine, prescription.dose_mg, prescription.times_per_day)
        fill_number = len(prescription.fills) + 1
        if medicine.controlled and not self.approvals.is_approved(rx_id, fill_number):
            self.approvals.request(rx_id, fill_number)
            raise ApprovalRequired(f"{rx_id} fill {fill_number} needs a pharmacist")
        picks = self._take(medicine, prescription.quantity, on)
        self.prescriptions.record_fill(rx_id, on)
        return self._receipt(medicine, prescription.quantity, picks, staff, on)

    def sell_over_counter(self, code: str, quantity: int, staff: Staff, on: date) -> Receipt:
        """Sell a medicine without a prescription and return the receipt.

        Controlled medicines are never sold this way; asking for one raises
        ApprovalRequired.
        """
        medicine = self.stock.medicine(code)
        if medicine.controlled:
            raise ApprovalRequired(f"{medicine.name} needs a prescription")
        picks = self._take(medicine, quantity, on)
        return self._receipt(medicine, quantity, picks, staff, on)

    def _take(self, medicine: Medicine, quantity: int, on: date) -> list[Pick]:
        """Take units from stock, logging the failure before passing it on."""
        try:
            picks = self.stock.take(medicine.code, quantity, on)
        except Exception:
            logger.exception("could not take %s x %s", quantity, medicine.code)
            raise
        for pick in picks:
            if (pick.expiry - on).days <= 30:
                self.warnings.append(f"{medicine.name} lot {pick.lot} is short-dated")
        return picks

    def _receipt(
        self, medicine: Medicine, quantity: int, picks: list[Pick], staff: Staff, on: date
    ) -> Receipt:
        """Write the receipt for one medicine."""
        receipt = self.receipt_book.new_receipt(on, staff.name)
        description = f"{medicine.name} {medicine.strength_mg} mg"
        receipt.lines.append(
            ReceiptLine(description, quantity, medicine.unit_price, tuple(picks))
        )
        return receipt
