"""Cancellation policy: what a guest pays when cancelling a reservation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from hotel import reservations
from hotel.rates import to_money

FREE_CANCELLATION_DAYS = 7
SHORT_NOTICE_DAYS = 2
LAST_MINUTE_SHARE = Decimal("0.5")


def fee_for(reservation: reservations.Reservation, today: date) -> Decimal:
    """Return the fee for cancelling `reservation` on `today`.

    Only a confirmed reservation costs anything to cancel:
    - 7 or more days before check-in, cancelling is free;
    - 2 to 6 days before, the guest pays the average price of one night;
    - with less notice, the guest pays half the price of the stay.
    """
    if reservation.status is not reservations.Status.CONFIRMED:
        return Decimal("0.00")
    notice = (reservation.check_in - today).days
    if notice >= FREE_CANCELLATION_DAYS:
        return Decimal("0.00")
    if notice >= SHORT_NOTICE_DAYS:
        return to_money(reservation.price / reservation.nights)
    return to_money(reservation.price * LAST_MINUTE_SHARE)
