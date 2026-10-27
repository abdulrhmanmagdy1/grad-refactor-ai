from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from rental.contracts import Booking, RentalDesk, ReturnReport, late_days, rental_days
from rental.fleet import Branch, Fleet, Vehicle
from rental.staff import Staff

T0 = datetime(2026, 6, 1, 10, 0)


def make_desk() -> RentalDesk:
    fleet = Fleet()
    fleet.add_branch(Branch("CAI", "Cairo Downtown", "Cairo"))
    fleet.add_branch(Branch("ALX", "Alexandria Corniche", "Alexandria"))
    fleet.add_vehicle(Vehicle("ECO-1", "economy", "CAI", 10_000))
    fleet.add_vehicle(Vehicle("ECO-2", "economy", "CAI", 20_000))
    fleet.add_vehicle(Vehicle("ECO-3", "economy", "CAI", 2_000_000))
    fleet.add_vehicle(Vehicle("SUV-1", "suv", "CAI", 30_000))
    return RentalDesk(fleet)


def rent(desk: RentalDesk, plate: str, age: int, dropoff: str, days: int):
    # Extras are passed explicitly so that tests do not depend on each other.
    return desk.open_contract(Booking(plate, "Driver", age, dropoff, T0, days), [])


def test_B1_started_days_are_billed_as_whole_days():
    assert rental_days(T0, T0 + timedelta(hours=25)) == 2
    assert rental_days(T0, T0 + timedelta(days=1, minutes=1)) == 2
    assert rental_days(T0, T0 + timedelta(hours=49)) == 3
    assert rental_days(T0, T0 + timedelta(days=1)) == 1
    assert rental_days(T0, T0 + timedelta(hours=2)) == 1


def test_B2_late_return_is_charged():
    desk = make_desk()
    contract = rent(desk, "ECO-1", 40, "CAI", 2)
    returned = contract.due_at + timedelta(hours=3)
    bill = desk.return_vehicle(contract.number, ReturnReport("CAI", returned, 10_300))
    assert bill.amount_of("late return") == Decimal("48.00")


def test_B2_early_return_has_no_late_charge():
    desk = make_desk()
    contract = rent(desk, "ECO-1", 40, "CAI", 4)
    returned = contract.due_at - timedelta(days=2)
    bill = desk.return_vehicle(contract.number, ReturnReport("CAI", returned, 10_300))
    assert bill.amount_of("late return") == Decimal("0.00")


def test_B3_young_driver_surcharge_does_not_leak_into_later_contracts():
    desk = make_desk()
    young = desk.open_contract(Booking("ECO-1", "Nour", 22, "CAI", T0, 2))
    adult = desk.open_contract(Booking("ECO-2", "Lina", 40, "CAI", T0, 2))
    assert "young-driver" in young.extras
    assert "young-driver" not in adult.extras
    assert adult.extras == []


def test_S1_counter_agent_cannot_waive_damage():
    desk = make_desk()
    contract = rent(desk, "SUV-1", 45, "ALX", 1)
    report = ReturnReport("ALX", contract.due_at, 30_100, Decimal("200.00"))
    desk.return_vehicle(contract.number, report)
    with pytest.raises(PermissionError):
        desk.waive_damage(contract.number, Staff("Ali", "agent", "ALX"), "customer is a regular")
    assert contract.bill.amount_of("damage") == Decimal("200.00")
    assert contract.waiver_reason is None


def test_keep_manager_can_waive_damage():
    desk = make_desk()
    contract = rent(desk, "SUV-1", 45, "ALX", 1)
    desk.return_vehicle(contract.number, ReturnReport("ALX", contract.due_at, 30_100, Decimal("200")))
    bill = desk.waive_damage(contract.number, Staff("Salma", "manager", "ALX"), "pre-existing")
    assert bill.amount_of("damage") == Decimal("0.00")


def test_keep_return_inside_grace_period_is_on_time():
    due = T0 + timedelta(days=2)
    assert late_days(due, due) == 0
    assert late_days(due, due + timedelta(minutes=59)) == 0
    assert late_days(due, due + timedelta(minutes=60)) == 1
    desk = make_desk()
    contract = rent(desk, "ECO-1", 40, "CAI", 2)
    returned = contract.due_at + timedelta(minutes=59)
    bill = desk.return_vehicle(contract.number, ReturnReport("CAI", returned, 10_100))
    assert bill.amount_of("late return") == Decimal("0.00")


def test_keep_retiring_high_mileage_cars_removes_every_match():
    desk = make_desk()
    desk.fleet.vehicle("ECO-2").odometer = 450_000
    retired = desk.fleet.retire_high_mileage(400_000)
    assert sorted(retired) == ["ECO-2", "ECO-3"]
    assert [v.plate for v in desk.fleet.vehicles_at("CAI")] == ["ECO-1", "SUV-1"]


def test_keep_retiring_keeps_cars_that_are_out():
    desk = make_desk()
    rent(desk, "ECO-3", 40, "CAI", 1)
    assert desk.fleet.retire_high_mileage(400_000) == []


def test_keep_one_way_invoice_and_deposit():
    desk = make_desk()
    contract = rent(desk, "ECO-1", 40, "ALX", 2)
    bill = desk.return_vehicle(contract.number, ReturnReport("ALX", contract.due_at, 10_500))
    assert bill.amount_of("one-way drop-off") == Decimal("55.00")
    assert bill.amount_of("excess mileage") == Decimal("20.00")
    assert bill.subtotal == Decimal("139.00")
    assert bill.balance_due == Decimal("158.46") - Decimal("250.00")
    assert desk.fleet.vehicle("ECO-1").branch_code == "ALX"
