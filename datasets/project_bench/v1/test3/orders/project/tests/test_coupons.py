from datetime import date
from decimal import Decimal

import pytest

from orders.coupons import Coupon, CouponBook, CouponError

TODAY = date(2026, 6, 1)


@pytest.fixture
def book() -> CouponBook:
    book = CouponBook()
    book.add(Coupon("SUMMER-10", percent_off=Decimal("10"), expires=date(2026, 6, 30)))
    book.add(Coupon("FIVE", amount_off=Decimal("5.00"), min_subtotal=Decimal("30.00")))
    book.add(Coupon("WELCOME", amount_off=Decimal("8.00"), single_use=True))
    book.add(Coupon("OLD", percent_off=Decimal("20"), active=False))
    return book


def test_codes_ignore_case_spaces_and_dashes(book: CouponBook) -> None:
    coupon = book.validate(" summer10 ", Decimal("50.00"), "c1", TODAY)
    assert coupon.code == "SUMMER-10"


def test_percent_discount_is_rounded_to_cents(book: CouponBook) -> None:
    coupon = book.validate("SUMMER-10", Decimal("33.35"), "c1", TODAY)
    assert coupon.discount(Decimal("33.35")) == Decimal("3.34")


def test_fixed_discount_never_exceeds_subtotal() -> None:
    assert Coupon("BIG", amount_off=Decimal("50.00")).discount(Decimal("20.00")) == Decimal("20.00")


def test_coupon_needs_exactly_one_kind_of_discount(book: CouponBook) -> None:
    with pytest.raises(CouponError):
        book.add(Coupon("NONE"))


@pytest.mark.parametrize(
    ("code", "subtotal", "today"),
    [
        ("NOPE", Decimal("50.00"), TODAY),
        ("OLD", Decimal("50.00"), TODAY),
        ("SUMMER-10", Decimal("50.00"), date(2026, 7, 1)),
        ("FIVE", Decimal("29.99"), TODAY),
    ],
)
def test_invalid_coupons_are_refused(
    book: CouponBook, code: str, subtotal: Decimal, today: date
) -> None:
    with pytest.raises(CouponError):
        book.validate(code, subtotal, "c1", today)


def test_single_use_coupon_works_once_per_customer(book: CouponBook) -> None:
    coupon = book.validate("WELCOME", Decimal("20.00"), "c1", TODAY)
    book.redeem(coupon, "c1")
    with pytest.raises(CouponError):
        book.validate("WELCOME", Decimal("20.00"), "c1", TODAY)
    assert book.validate("WELCOME", Decimal("20.00"), "c2", TODAY) is coupon
