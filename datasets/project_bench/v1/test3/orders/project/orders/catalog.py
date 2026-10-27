"""Products, their variants and the stock on hand."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


class StockError(Exception):
    """Raised when there is not enough stock, or the sku does not exist."""


@dataclass
class Variant:
    """One buyable version of a product, for example a colour and size."""

    sku: str
    product_id: str
    label: str
    price: Decimal
    weight_kg: Decimal
    stock: int = 0


@dataclass
class Product:
    """A product and its variants, keyed by sku."""

    product_id: str
    name: str
    variants: dict[str, Variant] = field(default_factory=dict)


class Catalog:
    """Every product on sale and the stock of each variant.

    Stock is taken when an order is placed and put back when an order is
    cancelled or returned.
    """

    def __init__(self) -> None:
        self.products: dict[str, Product] = {}
        self._variants: dict[str, Variant] = {}

    def add_product(self, product: Product) -> None:
        """Put a product and all its variants on sale."""
        self.products[product.product_id] = product
        for variant in product.variants.values():
            self._variants[variant.sku] = variant

    def variant(self, sku: str) -> Variant:
        """Return the variant with this sku."""
        try:
            return self._variants[sku]
        except KeyError:
            raise StockError(f"unknown sku {sku}") from None

    def reserve(self, wanted: dict[str, int]) -> None:
        """Take ``wanted`` quantities out of stock, all of them or none."""
        short = [sku for sku, quantity in wanted.items() if self.variant(sku).stock < quantity]
        if short:
            raise StockError(f"not enough stock for {', '.join(sorted(short))}")
        for sku, quantity in wanted.items():
            self.variant(sku).stock -= quantity

    def release(self, returned: dict[str, int]) -> None:
        """Put quantities back into stock."""
        for sku, quantity in returned.items():
            self.variant(sku).stock += quantity
