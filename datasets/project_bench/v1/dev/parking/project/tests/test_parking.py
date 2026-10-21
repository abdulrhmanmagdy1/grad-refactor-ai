from datetime import date, datetime, timedelta

import pytest

from parking.desk import ParkingDesk
from parking.garage import Garage
from parking.permits import PermitRegistry
from parking.rates import RateCard
from parking.report import daily_revenue, report_from_log
from parking.storage import TicketLog

NINE = datetime(2026, 3, 2, 9, 0)


def make_garage() -> Garage:
    garage = Garage()
    garage.add_level(1, {"standard": 2, "ev": 1})
    garage.add_level(2, {"standard": 3, "compact": 2})
    return garage


def make_desk() -> ParkingDesk:
    rates = RateCard(hourly=3.0, daily_cap=20.0)
    return ParkingDesk(make_garage(), rates, PermitRegistry(), TicketLog())


def test_cars_fill_the_lowest_level_first():
    garage = make_garage()
    assert garage.park("AA-1").code == "L1-001"
    assert garage.park("AA-2").code == "L1-002"
    assert garage.park("AA-3").code == "L2-001"
    assert garage.park("EV-1", "ev").code == "L1-003"


def test_no_free_space_of_a_kind():
    garage = make_garage()
    garage.park("C-1", "compact")
    garage.park("C-2", "compact")
    with pytest.raises(LookupError):
        garage.park("C-3", "compact")


def test_occupancy_per_level():
    garage = make_garage()
    garage.park("AA-1")
    garage.park("C-1", "compact")
    assert garage.occupancy() == {1: pytest.approx(1 / 3), 2: pytest.approx(1 / 5)}


def test_short_stays_are_free_and_a_day_is_capped():
    card = RateCard(hourly=3.0, daily_cap=20.0)
    assert card.charge(NINE, NINE + timedelta(minutes=10)) == 0.0
    assert card.charge(NINE, NINE + timedelta(hours=2)) == 6.0
    assert card.charge(NINE, NINE + timedelta(hours=9)) == 20.0


def test_a_stay_from_entry_to_exit():
    desk = make_desk()
    ticket = desk.enter("AB-123", NINE)
    closed = desk.leave(ticket.ticket_id, NINE + timedelta(hours=3))
    assert closed.amount == 9.0
    assert desk.garage.where_is("AB-123") is None
    assert [t.ticket_id for t in desk.log.for_plate("AB-123")] == [ticket.ticket_id]
    assert "incl. VAT 1.50" in desk.receipt(closed)


def test_permit_holders_park_free():
    desk = make_desk()
    desk.permits.issue("AB-123", "Sara", date(2026, 3, 1))
    ticket = desk.enter("AB-123", NINE)
    assert desk.leave(ticket.ticket_id, NINE + timedelta(hours=5)).amount == 0.0


def test_a_permit_runs_for_whole_months():
    permits = PermitRegistry()
    permit = permits.issue("AB-123", "Sara", date(2026, 3, 15), months=1)
    assert permit.expires == date(2026, 4, 15)
    assert permits.is_valid("AB-123", date(2026, 4, 14))
    assert not permits.is_valid("AB-123", date(2026, 4, 15))


def test_monthly_report():
    desk = make_desk()
    first = desk.enter("AB-123", NINE)
    desk.leave(first.ticket_id, NINE + timedelta(hours=2))
    second = desk.enter("XY-999", NINE + timedelta(days=1))
    desk.leave(second.ticket_id, NINE + timedelta(days=1, hours=1))
    desk.permits.issue("PP-777", "Omar", date(2026, 3, 10))
    assert daily_revenue(desk.log.all()) == {date(2026, 3, 2): 6.0, date(2026, 3, 3): 3.0}
    text = report_from_log(desk.log, desk.permits, 2026, 3)
    assert "Permits sold: 1" in text
    assert "Total          99.00" in text
