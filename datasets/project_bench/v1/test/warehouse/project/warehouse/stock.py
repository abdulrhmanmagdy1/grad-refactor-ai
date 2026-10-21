"""Stock levels per bin and reservations for open customer orders."""

from __future__ import annotations


class InsufficientStock(Exception):
    """Raised when a request needs more units than the warehouse has."""


class StockLedger:
    """Units of each SKU held in each bin, plus units promised to open orders."""

    def __init__(self) -> None:
        self._bins: dict[str, dict[str, int]] = {}
        self._reserved: dict[str, int] = {}

    def receive(self, sku: str, bin_code: str, quantity: int) -> None:
        """Put ``quantity`` units of ``sku`` away into ``bin_code``."""
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        contents = self._bins.setdefault(bin_code, {})
        contents[sku] = contents.get(sku, 0) + quantity

    def remove(self, sku: str, bin_code: str, quantity: int) -> None:
        """Take ``quantity`` units of ``sku`` out of ``bin_code``."""
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        held = self._bins.get(bin_code, {}).get(sku, 0)
        if quantity > held:
            raise InsufficientStock(f"{bin_code} holds {held} of {sku}, not {quantity}")
        self._bins[bin_code][sku] = held - quantity

    def bins_for(self, sku: str) -> dict[str, int]:
        """Bins that hold ``sku`` and how many units each holds, as a new dict."""
        return {
            code: contents[sku]
            for code, contents in self._bins.items()
            if contents.get(sku, 0) > 0
        }

    def on_hand(self, sku: str) -> int:
        """Units of ``sku`` across all bins."""
        return sum(self.bins_for(sku).values())

    def reserved(self, sku: str) -> int:
        """Units of ``sku`` promised to open customer orders."""
        return self._reserved.get(sku, 0)

    def available(self, sku: str) -> int:
        """Units of ``sku`` that can still be promised: on hand less reserved, never negative."""
        return max(0, self.on_hand(sku) - self.reserved(sku))

    def reserve(self, sku: str, quantity: int) -> None:
        """Promise ``quantity`` units to an order; InsufficientStock if they are not available."""
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        free = self.available(sku)
        if quantity > free:
            raise InsufficientStock(f"only {free} of {sku} available, not {quantity}")
        self._reserved[sku] = self.reserved(sku) + quantity

    def release(self, sku: str, quantity: int) -> None:
        """Drop ``quantity`` units from the reservation of ``sku`` (picked or cancelled)."""
        self._reserved[sku] = max(0, self.reserved(sku) - quantity)

    def skus(self) -> list[str]:
        """Every SKU that some bin holds, sorted."""
        return sorted(
            {sku for contents in self._bins.values() for sku, units in contents.items() if units > 0}
        )

    def prune_empty_bins(self) -> list[str]:
        """Drop zero entries, forget bins left with nothing, and return those bin codes."""
        emptied = []
        for bin_code, contents in list(self._bins.items()):
            for sku in [code for code, units in contents.items() if units == 0]:
                del contents[sku]
            if not contents:
                del self._bins[bin_code]
                emptied.append(bin_code)
        return sorted(emptied)
