"""Guest invoices and the archive they are filed in."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from hotel.rates import to_money
from hotel.reservations import Reservation, Status

VAT_RATE = Decimal("0.14")


@dataclass(frozen=True)
class Extra:
    """Something charged on top of the room: minibar, laundry, parking..."""

    description: str
    amount: Decimal


@dataclass(frozen=True)
class Invoice:
    """A finished invoice. `total` is the subtotal plus VAT."""

    reference: str
    guest: str
    lines: tuple[tuple[str, Decimal], ...]
    subtotal: Decimal
    vat: Decimal
    total: Decimal

    def render(self) -> str:
        """Plain-text layout used for printing and for the archive."""
        rows = [f"Invoice {self.reference}", f"Guest: {self.guest}", ""]
        rows.extend(f"{label:<40}{amount:>12}" for label, amount in self.lines)
        rows.append("")
        rows.append(f"{'Subtotal':<40}{self.subtotal:>12}")
        rows.append(f"{'VAT':<40}{self.vat:>12}")
        rows.append(f"{'Total':<40}{self.total:>12}")
        return "\n".join(rows) + "\n"


def build_invoice(
    reservation: Reservation,
    extras: Sequence[Extra] = (),
    vat_rate: Decimal = VAT_RATE,
) -> Invoice:
    """Build the invoice for a reservation.

    A cancelled reservation is billed its cancellation fee and nothing else. Any other
    reservation is billed the room price plus every extra. VAT is charged on the whole
    subtotal, room and extras alike.
    """
    if reservation.status is Status.CANCELLED:
        room_charge = reservation.cancellation_fee
        lines = [("Cancellation fee", room_charge)]
    else:
        room_charge = reservation.price
        lines = [(f"Room {reservation.room_number}, {reservation.nights} night(s)", room_charge)]
        lines.extend((extra.description, extra.amount) for extra in extras)
    subtotal = sum((amount for _, amount in lines), Decimal("0.00"))
    vat = to_money(subtotal * vat_rate)
    return Invoice(
        reference=f"INV-{reservation.reference}",
        guest=reservation.guest,
        lines=tuple(lines),
        subtotal=subtotal,
        vat=vat,
        total=subtotal + vat,
    )


class InvoiceArchive:
    """Rendered invoices kept as text files in one directory.

    The front desk looks an invoice up by the file name printed on the guest's receipt.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def file_name(invoice: Invoice) -> str:
        """Name of the file an invoice is stored under."""
        return f"{invoice.reference}.txt"

    def store(self, invoice: Invoice) -> Path:
        """Write the invoice into the archive and return its path."""
        path = self.root / self.file_name(invoice)
        path.write_text(invoice.render(), encoding="utf-8")
        return path

    def names(self) -> list[str]:
        """File names of every archived invoice, sorted."""
        return sorted(path.name for path in self.root.glob("*.txt"))

    def read(self, name: str) -> str:
        """Return the text of the archived invoice stored under `name`.

        Only invoices filed in this archive can be read this way.
        """
        root = self.root.resolve()
        path = (root / name).resolve()
        if path.parent != root:
            raise ValueError(f"{name!r} is not an invoice in this archive")
        return path.read_text(encoding="utf-8")
