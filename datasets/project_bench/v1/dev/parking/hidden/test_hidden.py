from datetime import date, datetime, timedelta

import pytest

from parking.desk import LOST_TICKET_FEE, ParkingDesk
from parking.garage import Garage
from parking.models import Permit, Ticket
from parking.permits import PermitRegistry, add_months
from parking.rates import RateCard
from parking.report import busiest_days, revenue_report, vat_split
from parking.storage import TicketLog

NINE = datetime(2026, 3, 2, 9, 0)
MIDNIGHT = datetime(2026, 3, 2, 0, 0)


def closed(ticket_id: str, plate: str, left: datetime, amount: float, hours: int = 2) -> Ticket:
    return Ticket(ticket_id, plate, "L1-001", left - timedelta(hours=hours), left, amount)


def make_desk() -> ParkingDesk:
    garage = Garage()
    garage.add_level(1, {"standard": 2})
    garage.add_level(2, {"standard": 2})
    return ParkingDesk(garage, RateCard(hourly=3.0, daily_cap=20.0), PermitRegistry(), TicketLog())


def test_B1_a_started_hour_is_billed_in_full():
    card = RateCard(hourly=2.0, daily_cap=50.0)
    assert card.charge(NINE, NINE + timedelta(minutes=61)) == 4.0
    assert card.charge(NINE, NINE + timedelta(hours=2, minutes=10)) == 6.0
    assert card.charge(NINE, NINE + timedelta(minutes=40)) == 2.0


def test_B2_every_day_of_a_long_stay_has_its_own_cap():
    card = RateCard(hourly=3.0, daily_cap=20.0)
    assert card.charge(MIDNIGHT, MIDNIGHT + timedelta(days=3)) == 60.0
    assert card.charge(MIDNIGHT, MIDNIGHT + timedelta(hours=50)) == 46.0
    assert card.charge(MIDNIGHT, MIDNIGHT + timedelta(hours=40)) == 40.0


def test_B3_busiest_days_come_highest_first():
    tickets = [
        closed("T1", "AA-1", datetime(2026, 3, 2, 12), 10.0),
        closed("T2", "AA-2", datetime(2026, 3, 3, 12), 40.0),
        closed("T3", "AA-3", datetime(2026, 3, 4, 12), 25.0),
        closed("T4", "AA-4", datetime(2026, 3, 3, 18), 5.0),
    ]
    assert busiest_days(tickets, 2) == [(date(2026, 3, 3), 45.0), (date(2026, 3, 4), 25.0)]
    assert busiest_days(tickets, 1) == [(date(2026, 3, 3), 45.0)]


def test_S1_plate_lookup_cannot_be_turned_into_other_sql():
    log = TicketLog()
    log.record(closed("T1", "AB-123", NINE, 6.0))
    log.record(closed("T2", "XY-999", NINE, 9.0))
    try:
        found = log.for_plate("nobody' OR '1'='1")
    except ValueError:
        found = []
    assert found == []
    assert [ticket.ticket_id for ticket in log.for_plate("AB-123")] == ["T1"]


def test_keep_tickets_sort_only_by_known_columns():
    log = TicketLog()
    log.record(closed("T1", "AA-1", NINE, 9.0))
    log.record(closed("T2", "BB-2", NINE + timedelta(hours=1), 3.0))
    log.record(closed("T3", "CC-3", NINE + timedelta(hours=2), 6.0))
    assert [ticket.ticket_id for ticket in log.all("amount")] == ["T2", "T3", "T1"]
    assert [ticket.ticket_id for ticket in log.all()] == ["T1", "T2", "T3"]
    with pytest.raises(ValueError):
        log.all("amount; DROP TABLE tickets")
    assert len(log.all()) == 3


def test_keep_add_months_moves_to_the_end_of_a_short_month():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert add_months(date(2026, 11, 15), 2) == date(2027, 1, 15)
    assert add_months(date(2026, 12, 1), 1) == date(2027, 1, 1)
    assert add_months(date(2026, 3, 31), 12) == date(2027, 3, 31)


def test_keep_permit_is_valid_up_to_the_day_before_it_expires():
    permits = PermitRegistry()
    permits.issue("AB-123", "Sara", date(2026, 1, 31), months=1)
    assert permits.is_valid("AB-123", date(2026, 2, 27))
    assert not permits.is_valid("AB-123", date(2026, 2, 28))
    assert not permits.is_valid("AB-123", date(2026, 1, 30))


def test_keep_grace_period_and_one_day_cap():
    card = RateCard(hourly=3.0, daily_cap=20.0)
    assert card.charge(NINE, NINE + timedelta(minutes=15)) == 0.0
    assert card.charge(NINE, NINE + timedelta(hours=1)) == 3.0
    assert card.charge(NINE, NINE + timedelta(hours=10)) == 20.0
    with pytest.raises(ValueError):
        card.charge(NINE, NINE - timedelta(minutes=1))


def test_keep_lost_ticket_pays_the_stay_and_the_fee():
    desk = make_desk()
    desk.enter("AB-123", NINE)
    ticket = desk.lost_ticket("AB-123", NINE + timedelta(hours=2))
    assert ticket.amount == 6.0 + LOST_TICKET_FEE
    assert desk.open == {}


def test_keep_vat_is_the_included_part_of_the_price():
    assert vat_split(120.0) == (100.0, 20.0)
    desk = make_desk()
    ticket = desk.enter("AB-123", NINE)
    desk.leave(ticket.ticket_id, NINE + timedelta(hours=4))
    assert "12.00 (incl. VAT 2.00)" in desk.receipt(ticket)


def test_keep_monthly_report_sections():
    tickets = [
        Ticket("T1", "AA-1", "L1-001", datetime(2026, 3, 2, 9), datetime(2026, 3, 2, 11), 6.0),
        Ticket("T2", "AA-2", "L2-004", datetime(2026, 3, 2, 9), datetime(2026, 3, 2, 10), 0.0),
        Ticket("T3", "AA-3", "L2-001", datetime(2026, 3, 5, 9), datetime(2026, 3, 5, 12), 9.0),
        Ticket("T4", "AA-4", "L1-002", datetime(2026, 2, 27, 9), datetime(2026, 2, 27, 10), 3.0),
    ]
    permits = [
        Permit("PP-1", "Omar", date(2026, 3, 10), date(2026, 4, 10), 90.0),
        Permit("PP-2", "Lina", date(2026, 2, 10), date(2026, 3, 10), 90.0),
    ]
    text = revenue_report(tickets, permits, 2026, 3)
    assert "2026-03-02        6.00" in text
    assert "2026-03-05        9.00" in text
    assert "2026-02-27" not in text
    assert "L1                6.00" in text
    assert "L2                9.00" in text
    assert "Stays: 3 (1 free), average 120 min" in text
    assert "Permits sold: 1" in text
    assert "Total         105.00" in text
    assert "  net          87.50" in text
    assert "  VAT          17.50" in text
