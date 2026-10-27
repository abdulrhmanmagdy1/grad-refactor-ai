"""Sales receipts: line totals, VAT and the printed text."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from pharmacy import inventory
from pharmacy.models import Pick

VAT_RATE = Decimal("0.05")
CENT = Decimal("0.01")


def format_money(amount: Decimal) -> str:
    """Format an amount with two decimals and a currency code, e.g. ``12.50 OMR``."""
    return f"{amount.quantize(CENT, rounding=ROUND_HALF_UP)} OMR"


@dataclass(frozen=True)
class ReceiptLine:
    """One medicine on a receipt; ``picks`` say which batches the units came from."""

    description: str
    quantity: int
    unit_price: Decimal
    picks: tuple[Pick, ...] = ()

    @property
    def amount(self) -> Decimal:
        """Quantity times unit price, before VAT, rounded half up to the cent."""
        return (self.unit_price * self.quantity).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class Receipt:
    """A finished sale."""

    number: str
    issued_on: date
    served_by: str
    lines: list[ReceiptLine] = field(default_factory=list)

    @property
    def subtotal(self) -> Decimal:
        """The sum of the line amounts, before VAT."""
        return sum((line.amount for line in self.lines), Decimal("0"))

    @property
    def vat(self) -> Decimal:
        """VAT on the subtotal, rounded half up to the cent."""
        return (self.subtotal * VAT_RATE).quantize(CENT, rounding=ROUND_HALF_UP)

    @property
    def total(self) -> Decimal:
        """What the customer pays."""
        return self.subtotal + self.vat


class ReceiptBook:
    """Hands out receipt numbers in sequence: R000001, R000002, ..."""

    def __init__(self) -> None:
        self._last = 0
        self.issued: list[Receipt] = []

    def new_receipt(self, issued_on: date, served_by: str) -> Receipt:
        """Start a receipt with the next number and remember it."""
        self._last += 1
        receipt = Receipt(f"R{self._last:06d}", issued_on, served_by)
        self.issued.append(receipt)
        return receipt


def _line_discount(amount: Decimal, percent: int) -> Decimal:
    """Return ``amount`` reduced by ``percent`` per cent, rounded to the cent."""
    reduced = amount * (Decimal(100) - Decimal(percent)) / Decimal(100)
    return reduced.quantize(CENT, rounding=ROUND_HALF_UP)


def render(receipt: Receipt, stock: inventory.Inventory) -> str:
    """Return the receipt as printed text.

    Each line shows the batches its units came from; a batch that expires within a
    month of the sale is marked SHORT-DATED so the customer is told.
    """
    out = [f"Receipt {receipt.number}  {receipt.issued_on.isoformat()}  ({receipt.served_by})"]
    for line in receipt.lines:
        out.append(f"{line.quantity} x {line.description}  {format_money(line.amount)}")
        for pick in line.picks:
            note = ""
            if (pick.expiry - receipt.issued_on).days <= 30:
                note = "  SHORT-DATED"
            out.append(f"    {pick.quantity} from {inventory.describe_pick(stock, pick)}{note}")
    out.append(f"Subtotal {format_money(receipt.subtotal)}")
    out.append(f"VAT {format_money(receipt.vat)}")
    out.append(f"Total {format_money(receipt.total)}")
    return "\n".join(out)
