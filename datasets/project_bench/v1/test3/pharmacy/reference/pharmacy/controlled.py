"""Approvals for controlled medicines.

A controlled medicine may only be handed over after a pharmacist has approved that
particular prescription fill. Every approval is kept for the controlled-drugs register.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pharmacy.models import Staff


@dataclass(frozen=True)
class Approval:
    """A pharmacist's sign-off for one fill of one prescription."""

    rx_id: str
    fill_number: int
    approved_by: str
    approved_at: datetime


class ApprovalRegister:
    """Pending requests and granted approvals, keyed by prescription and fill number."""

    def __init__(self) -> None:
        self._pending: set[tuple[str, int]] = set()
        self._granted: dict[tuple[str, int], Approval] = {}

    def request(self, rx_id: str, fill_number: int) -> None:
        """Ask for approval of a fill; asking twice for the same fill is harmless."""
        key = (rx_id, fill_number)
        if key not in self._granted:
            self._pending.add(key)

    def pending(self) -> list[tuple[str, int]]:
        """Return the fills waiting for a pharmacist, in a stable order."""
        return sorted(self._pending)

    def approve(self, rx_id: str, fill_number: int, staff: Staff, at: datetime) -> Approval:
        """Approve a requested fill.

        Only an active pharmacist may approve; anyone else gets PermissionError. Raises
        KeyError when the fill was never requested.
        """
        key = (rx_id, fill_number)
        if key not in self._pending:
            raise KeyError(key)
        if staff.role != "pharmacist":
            raise PermissionError(f"{staff.name} is not a pharmacist")
        if not staff.active:
            raise PermissionError(f"{staff.name} is not on duty")
        approval = Approval(rx_id, fill_number, staff.staff_id, at)
        self._pending.discard(key)
        self._granted[key] = approval
        return approval

    def is_approved(self, rx_id: str, fill_number: int) -> bool:
        """Return True when a pharmacist has approved this fill."""
        return (rx_id, fill_number) in self._granted

    def register_entries(self) -> list[Approval]:
        """Return every approval, oldest first, for the controlled-drugs register."""
        return sorted(self._granted.values(), key=lambda a: a.approved_at)
