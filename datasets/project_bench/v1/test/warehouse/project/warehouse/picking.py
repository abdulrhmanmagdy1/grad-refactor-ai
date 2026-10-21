"""Planning pick tasks for customer orders and grouping orders into waves."""

from __future__ import annotations

from collections.abc import Iterable

from warehouse.models import CustomerLine, PickTask
from warehouse.stock import InsufficientStock, StockLedger


def plan_picks(ledger: StockLedger, lines: Iterable[CustomerLine]) -> list[PickTask]:
    """Plan which bins every customer line is picked from.

    A line takes from the bins holding its SKU, smallest quantity first so that
    part-used bins get emptied; ties go to the lower bin code. Units planned for
    one line are not offered to a later one. Raises InsufficientStock when the
    bins cannot cover a line. The ledger itself is not changed.
    """
    left: dict[str, dict[str, int]] = {}
    tasks: list[PickTask] = []
    for line in lines:
        if line.sku not in left:
            left[line.sku] = ledger.bins_for(line.sku)
        tasks.extend(_take_from_bins(line, left[line.sku]))
    return tasks


def _take_from_bins(line: CustomerLine, bins: dict[str, int]) -> list[PickTask]:
    """Pick tasks that cover ``line`` from ``bins``, lowering ``bins`` as it goes."""
    if sum(bins.values()) < line.quantity:
        raise InsufficientStock(f"not enough {line.sku} in the bins for order {line.order_id}")
    needed = line.quantity
    tasks = []
    for bin_code in sorted(bins, key=lambda code: (bins[code], code)):
        take = min(needed, bins[bin_code])
        if take > 0:
            bins[bin_code] -= take
            needed -= take
            tasks.append(PickTask(line.order_id, line.sku, bin_code, take))
    return tasks


def confirm_picks(ledger: StockLedger, tasks: Iterable[PickTask]) -> int:
    """Take picked units out of their bins and release their reservations.

    Returns the number of units picked.
    """
    picked = 0
    for task in tasks:
        ledger.remove(task.sku, task.bin_code, task.quantity)
        ledger.release(task.sku, task.quantity)
        picked += task.quantity
    return picked


class WaveBuilder:
    """Collects customer lines into pick waves of at most ``max_orders`` orders."""

    def __init__(self, max_orders: int) -> None:
        if max_orders < 1:
            raise ValueError("a wave needs room for at least one order")
        self.max_orders = max_orders
        self._lines: list[CustomerLine] = []
        self._orders: set[str] = set()

    def add(self, line: CustomerLine) -> bool:
        """Add ``line`` to the open wave.

        Lines of an order already in the wave are always accepted. A line of a
        new order is refused (False, nothing added) once the wave is full.
        """
        if line.order_id not in self._orders and len(self._orders) >= self.max_orders:
            return False
        self._orders.add(line.order_id)
        self._lines.append(line)
        return True

    def order_count(self) -> int:
        """Number of distinct orders in the open wave."""
        return len(self._orders)

    def release(self) -> list[CustomerLine]:
        """Close the open wave, return its lines, and start a new, empty wave."""
        lines = self._lines
        self._lines = []
        return lines
