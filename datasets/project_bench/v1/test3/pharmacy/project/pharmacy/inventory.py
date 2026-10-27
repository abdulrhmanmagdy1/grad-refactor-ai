"""Stock held per batch, sold first-expiring first (FEFO)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from pharmacy import receipts
from pharmacy.models import Batch, Medicine, Pick


class OutOfStock(Exception):
    """Raised when there are not enough sellable units to fill an order."""


class Inventory:
    """The formulary and the batches on the shelves.

    A batch can be sold up to and including its expiry date and never after it.
    """

    def __init__(self) -> None:
        self._medicines: dict[str, Medicine] = {}
        self._batches: dict[str, list[Batch]] = {}

    def add_medicine(self, medicine: Medicine) -> None:
        """Add a medicine to the formulary, replacing an entry with the same code."""
        self._medicines[medicine.code] = medicine
        self._batches.setdefault(medicine.code, [])

    def medicine(self, code: str) -> Medicine:
        """Return the formulary entry for ``code``; raises KeyError if it is unknown."""
        return self._medicines[code]

    def receive(self, batch: Batch) -> None:
        """Put a delivered batch on the shelf.

        Raises KeyError for a medicine that is not in the formulary and ValueError for a
        batch with no units.
        """
        if batch.medicine_code not in self._medicines:
            raise KeyError(batch.medicine_code)
        if batch.quantity <= 0:
            raise ValueError("a batch must contain at least one unit")
        self._batches[batch.medicine_code].append(batch)

    def sellable(self, code: str, on: date) -> list[Batch]:
        """Return the batches of ``code`` that still have units and have not expired."""
        return [b for b in self._batches.get(code, []) if b.quantity > 0 and b.expiry >= on]

    def on_hand(self, code: str, on: date) -> int:
        """Return how many units of ``code`` can be sold on the given day."""
        return sum(batch.quantity for batch in self.sellable(code, on))

    def take(self, code: str, quantity: int, on: date) -> list[Pick]:
        """Remove ``quantity`` units of ``code`` from stock and say where they came from.

        Units come from the batch that expires first, then the next one, and so on, so
        that short-dated stock leaves the shelf before newer deliveries. Raises
        OutOfStock, leaving the stock untouched, when there are not enough sellable units.
        """
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.on_hand(code, on) < quantity:
            raise OutOfStock(f"only {self.on_hand(code, on)} units of {code} left")
        picks: list[Pick] = []
        still_needed = quantity
        for batch in sorted(self.sellable(code, on), key=lambda b: b.expiry, reverse=True):
            taken = min(batch.quantity, still_needed)
            batch.quantity -= taken
            picks.append(Pick(code, batch.lot, batch.expiry, taken))
            still_needed -= taken
            if still_needed == 0:
                break
        return picks

    def remove_empty(self) -> int:
        """Drop batches with no units left and return how many were dropped."""
        dropped = 0
        for batches in self._batches.values():
            for batch in list(batches):
                if batch.quantity == 0:
                    batches.remove(batch)
                    dropped += 1
        return dropped

    def expiry_report(self, on: date, lines: list[str] = []) -> list[str]:
        """Return one line per batch that expires within the next month, soonest first.

        Lines are appended to ``lines`` when the caller passes a report to extend.
        """
        horizon = on + timedelta(days=30)
        batches = [b for code in self._batches for b in self.sellable(code, on)]
        for batch in sorted(batches, key=lambda b: (b.expiry, b.lot)):
            if batch.expiry <= horizon:
                name = self._medicines[batch.medicine_code].name
                lines.append(f"{batch.expiry.isoformat()}  {name}  lot {batch.lot}  x{batch.quantity}")
        return lines

    def stock_value(self, on: date) -> str:
        """Return the shelf value of all sellable stock, formatted as money."""
        total = Decimal("0")
        for code, medicine in self._medicines.items():
            total += medicine.unit_price * self.on_hand(code, on)
        return receipts.format_money(total)


def describe_pick(inventory: Inventory, pick: Pick) -> str:
    """Return a one-line description of a pick, as printed on labels and receipts."""
    medicine = inventory.medicine(pick.medicine_code)
    return f"{medicine.name} {medicine.strength_mg} mg, lot {pick.lot}, exp {pick.expiry.isoformat()}"
