"""Prescriptions on file, their refill limits and the dosage check."""

from __future__ import annotations

from datetime import date, timedelta

from pharmacy.models import Medicine, Prescription

VALID_FOR = timedelta(days=180)


class PrescriptionError(Exception):
    """Raised when a prescription cannot be filled."""


class DosageError(PrescriptionError):
    """Raised when a prescribed dose is above what the formulary allows."""


def check_dosage(medicine: Medicine, dose_mg: int, times_per_day: int) -> int:
    """Check a prescribed dose against the medicine's limits and return the daily total.

    The daily total is ``dose_mg * times_per_day``. Raises DosageError when a single dose
    is above ``medicine.max_single_mg``, when the daily total is above
    ``medicine.max_daily_mg``, or when either number is not positive.
    """
    if dose_mg <= 0 or times_per_day <= 0:
        raise DosageError("dose and frequency must be positive")
    daily_mg = dose_mg * times_per_day
    if dose_mg > medicine.max_single_mg:
        raise DosageError(f"{dose_mg} mg at once is above {medicine.max_single_mg} mg")
    if daily_mg > medicine.max_daily_mg:
        raise DosageError(f"{daily_mg} mg a day is above {medicine.max_daily_mg} mg")
    return daily_mg


class PrescriptionBook:
    """Every prescription the pharmacy holds, by id."""

    def __init__(self) -> None:
        self._by_id: dict[str, Prescription] = {}

    def add(self, prescription: Prescription) -> None:
        """File a new prescription; raises ValueError if the id is already on file."""
        if prescription.rx_id in self._by_id:
            raise ValueError(f"prescription {prescription.rx_id} is already on file")
        self._by_id[prescription.rx_id] = prescription

    def get(self, rx_id: str) -> Prescription:
        """Return the prescription; raises PrescriptionError if it is not on file."""
        try:
            return self._by_id[rx_id]
        except KeyError:
            raise PrescriptionError(f"no prescription {rx_id}") from None

    def for_patient(self, patient: str) -> list[Prescription]:
        """Return the patient's prescriptions, newest first."""
        found = [rx for rx in self._by_id.values() if rx.patient == patient]
        return sorted(found, key=lambda rx: rx.issued, reverse=True)

    @staticmethod
    def fills_left(prescription: Prescription) -> int:
        """Return how many more times the prescription can be filled."""
        return max(0, 1 + prescription.refills_allowed - len(prescription.fills))

    def check_fillable(self, rx_id: str, on: date) -> Prescription:
        """Return the prescription if it can be filled on ``on``.

        Raises PrescriptionError when it is not on file, was issued after ``on``, is
        older than its validity period, or has no fills left.
        """
        prescription = self.get(rx_id)
        if on < prescription.issued:
            raise PrescriptionError(f"{rx_id} is dated after {on.isoformat()}")
        if on > prescription.issued + VALID_FOR:
            raise PrescriptionError(f"{rx_id} has expired")
        if self.fills_left(prescription) == 0:
            raise PrescriptionError(f"{rx_id} has no refills left")
        return prescription

    def record_fill(self, rx_id: str, on: date) -> None:
        """Note that the prescription was filled on ``on``."""
        self.get(rx_id).fills.append(on)
