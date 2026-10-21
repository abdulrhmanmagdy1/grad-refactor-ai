"""Data types shared by the clinic modules."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


class AppointmentStatus(enum.Enum):
    """An appointment is booked, then completed, cancelled or missed (no-show)."""

    BOOKED = "booked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no-show"


@dataclass
class Patient:
    """A registered patient; ``id`` is None until the patient has been stored."""

    name: str
    birth_date: date
    phone: str = ""
    id: int | None = None


@dataclass
class Doctor:
    """A doctor, the fee for one visit and the weekly working hours.

    ``hours`` maps a weekday (0 = Monday ... 6 = Sunday) to the opening and closing
    time on that day; a missing weekday is a day off.
    """

    id: int
    name: str
    fee: Decimal
    hours: dict[int, tuple[time, time]] = field(default_factory=dict)


@dataclass
class Appointment:
    """A visit of a patient to a doctor from ``start`` up to, not including, ``end``."""

    id: int
    patient_id: int
    doctor_id: int
    start: datetime
    end: datetime
    status: AppointmentStatus = AppointmentStatus.BOOKED

    @property
    def holds_time(self) -> bool:
        """A cancelled appointment frees its time; every other status keeps it."""
        return self.status is not AppointmentStatus.CANCELLED

    def overlaps(self, start: datetime, end: datetime) -> bool:
        """True when this appointment shares time with ``start``-``end``.

        Appointments that only touch (one ends when the other starts) do not overlap.
        """
        return self.start < end and start < self.end


@dataclass(frozen=True)
class InsurancePolicy:
    """A patient's insurance.

    The insurer pays ``coverage_percent`` of each visit, up to ``annual_limit`` per
    calendar year, for visits from ``valid_from`` to ``valid_until`` (both included).
    """

    patient_id: int
    insurer: str
    coverage_percent: int
    annual_limit: Decimal
    valid_from: date
    valid_until: date


@dataclass(frozen=True)
class Invoice:
    """What a visit costs and who pays it; the two shares add up to ``total``."""

    appointment_id: int
    patient_id: int
    issued_on: date
    total: Decimal
    patient_share: Decimal
    insurer_share: Decimal = ZERO
    insurer: str = ""
