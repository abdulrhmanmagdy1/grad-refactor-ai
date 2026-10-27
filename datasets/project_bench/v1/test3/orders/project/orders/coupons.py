"""Coupon codes: percentage or fixed discounts with conditions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from orders.utils import money, normalize_code


class CouponError(Exception):
    """Raised when a coupon cannot be used."""


@dataclass
class Coupon:
    """A discount code.

    ``percent_off`` (10 means 10 %) or ``amount_off`` sets the discount. The coupon
    is valid while ``active``, up to and including ``expires``, on a subtotal of at
    least ``min_subtotal``; a ``single_use`` coupon works once per customer.
    """

    code: str
    percent_off: Decimal | None = None
    amount_off: Decimal | None = None
    min_subtotal: Decimal = Decimal("0.00")
    expires: date | None = None
    single_use: bool = False
    active: bool = True
    used_by: set[str] = field(default_factory=set)

    def discount(self, subtotal: Decimal) -> Decimal:
        """Discount on ``subtotal`` in cents; never more than the subtotal itself."""
        if self.percent_off is not None:
            off = money(subtotal * self.percent_off / 100)
        else:
            off = self.amount_off or Decimal("0.00")
        return min(off, subtotal)


class CouponBook:
    """The shop's coupons, looked up by normalised code."""

    def __init__(self) -> None:
        self.coupons: dict[str, Coupon] = {}

    def add(self, coupon: Coupon) -> None:
        """Make a coupon available; exactly one of percent_off and amount_off is set."""
        if (coupon.percent_off is None) == (coupon.amount_off is None):
            raise CouponError("a coupon needs either percent_off or amount_off")
        self.coupons[normalize_code(coupon.code)] = coupon

    def validate(self, code: str, subtotal: Decimal, customer_id: str, today: date) -> Coupon:
        """Return the coupon for ``code`` if this customer may use it on ``subtotal`` today."""
        coupon = self.coupons.get(normalize_code(code))
        if coupon is not None:
            if coupon.active:
                if coupon.expires is None or today <= coupon.expires:
                    if subtotal >= coupon.min_subtotal:
                        if not (coupon.single_use and customer_id in coupon.used_by):
                            return coupon
                        raise CouponError(f"{code} has already been used")
                    raise CouponError(f"{code} needs a subtotal of {coupon.min_subtotal}")
                raise CouponError(f"{code} expired on {coupon.expires}")
            raise CouponError(f"{code} is no longer active")
        raise CouponError(f"unknown coupon {code}")

    def redeem(self, coupon: Coupon, customer_id: str) -> None:
        """Record that the customer used the coupon."""
        coupon.used_by.add(customer_id)
