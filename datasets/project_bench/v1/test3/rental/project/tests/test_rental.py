from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from rental.contracts import Booking, RentalDesk, ReturnReport
from rental.fleet import Branch, Fleet, Vehicle, VehicleStatus
from rental.invoice import quote
from rental.report import branch_summary, overdue_contracts
from rental.staff import Staff

T0 = datetime(2026, 5, 4, 9, 0)


def make_desk() -> RentalDesk:
    fleet = Fleet()
    fleet.add_branch(Branch("CAI", "Cairo Downtown", "Cairo"))
    fleet.add_branch(Branch("ALX", "Alexandria Corniche", "Alexandria"))
    fleet.add_vehicle(Vehicle("ECO-1", "economy", "CAI", 12_000))
    fleet.add_vehicle(Vehicle("ECO-2", "economy", "CAI", 8_000))
    fleet.add_vehicle(Vehicle("SUV-1", "suv", "CAI", 30_000))
    fleet.add_vehicle(Vehicle("VAN-1", "van", "ALX", 5_000))
    return RentalDesk(fleet)


def test_available_lists_lowest_odometer_first():
    desk = make_desk()
    plates = [v.plate for v in desk.fleet.available("CAI", "economy")]
    assert plates == ["ECO-2", "ECO-1"]


def test_unknown_vehicle_class_is_refused():
    fleet = Fleet()
    fleet.add_branch(Branch("CAI", "Cairo Downtown", "Cairo"))
    with pytest.raises(ValueError):
        fleet.add_vehicle(Vehicle("X-1", "limousine", "CAI", 0))


def test_a_rented_car_cannot_be_rented_again():
    desk = make_desk()
    desk.open_contract(Booking("ECO-1", "Mona", 34, "CAI", T0, 2))
    with pytest.raises(ValueError):
        desk.open_contract(Booking("ECO-1", "Omar", 40, "CAI", T0, 1))


def test_on_time_return_bills_booked_days_and_extras():
    desk = make_desk()
    contract = desk.open_contract(Booking("ECO-1", "Mona", 34, "CAI", T0, 3), ["gps"])
    bill = desk.return_vehicle(contract.number, ReturnReport("CAI", T0 + timedelta(days=3), 12_400))
    assert bill.amount_of("rental economy") == Decimal("96.00")
    assert bill.amount_of("extra gps") == Decimal("15.00")
    assert bill.amount_of("excess mileage") == Decimal("0.00")
    assert bill.tax == Decimal("15.54")
    assert bill.balance_due == Decimal("126.54") - Decimal("250.00")


def test_excess_mileage_is_charged_per_kilometre():
    desk = make_desk()
    contract = desk.open_contract(Booking("SUV-1", "Karim", 45, "CAI", T0, 1))
    bill = desk.return_vehicle(contract.number, ReturnReport("CAI", T0 + timedelta(days=1), 30_350))
    assert bill.amount_of("excess mileage") == Decimal("15.00")


def test_one_way_rental_adds_the_fee_and_leaves_the_car_at_drop_off():
    desk = make_desk()
    contract = desk.open_contract(Booking("ECO-2", "Hana", 29, "ALX", T0, 2))
    assert contract.is_one_way
    bill = desk.return_vehicle(contract.number, ReturnReport("ALX", T0 + timedelta(days=2), 8_300))
    assert bill.amount_of("one-way drop-off") == Decimal("55.00")
    assert desk.fleet.vehicle("ECO-2").branch_code == "ALX"
    assert desk.fleet.vehicle("ECO-2").status is VehicleStatus.AVAILABLE


def test_return_at_the_wrong_branch_is_refused():
    desk = make_desk()
    contract = desk.open_contract(Booking("ECO-2", "Hana", 29, "ALX", T0, 2))
    with pytest.raises(ValueError):
        desk.return_vehicle(contract.number, ReturnReport("CAI", T0 + timedelta(days=2), 8_300))


def test_underage_driver_is_refused():
    desk = make_desk()
    with pytest.raises(ValueError):
        desk.open_contract(Booking("ECO-1", "Youssef", 19, "CAI", T0, 1))


def test_young_driver_pays_the_surcharge():
    desk = make_desk()
    contract = desk.open_contract(Booking("ECO-1", "Nour", 23, "CAI", T0, 2), ["child-seat"])
    assert contract.extras == ["child-seat", "young-driver"]


def test_manager_of_drop_off_branch_can_waive_damage():
    desk = make_desk()
    contract = desk.open_contract(Booking("VAN-1", "Adel", 50, "ALX", T0, 1))
    report = ReturnReport("ALX", T0 + timedelta(days=1), 5_100, Decimal("180.00"))
    assert desk.return_vehicle(contract.number, report).amount_of("damage") == Decimal("180.00")
    manager = Staff("Salma", "manager", "ALX")
    bill = desk.waive_damage(contract.number, manager, "scratch was there before")
    assert bill.amount_of("damage") == Decimal("0.00")
    assert contract.waiver_reason == "scratch was there before"


def test_staff_of_another_branch_cannot_waive_damage():
    desk = make_desk()
    contract = desk.open_contract(Booking("VAN-1", "Adel", 50, "ALX", T0, 1))
    desk.return_vehicle(contract.number, ReturnReport("ALX", T0 + timedelta(days=1), 5_100, Decimal("90")))
    with pytest.raises(PermissionError):
        desk.waive_damage(contract.number, Staff("Tarek", "manager", "CAI"), "goodwill")


def test_quote_includes_tax():
    assert quote("compact", 2, ["gps"], one_way=True) == Decimal("167.58")


def test_branch_summary_counts_cars_and_revenue():
    desk = make_desk()
    first = desk.open_contract(Booking("ECO-1", "Mona", 34, "CAI", T0, 1))
    desk.open_contract(Booking("SUV-1", "Karim", 45, "ALX", T0, 2))
    desk.return_vehicle(first.number, ReturnReport("CAI", T0 + timedelta(days=1), 12_100))
    summary = branch_summary(desk, "CAI")
    assert summary.available_by_class == {"economy": 2}
    assert summary.cars_out == 1
    assert branch_summary(desk, "ALX").returns_expected == 1
    assert summary.revenue == Decimal("36.48")


def test_overdue_contracts_lists_cars_not_back_in_time():
    desk = make_desk()
    late = desk.open_contract(Booking("ECO-1", "Mona", 34, "CAI", T0, 1))
    desk.open_contract(Booking("ECO-2", "Omar", 40, "CAI", T0, 5))
    assert overdue_contracts(desk, T0 + timedelta(days=2)) == [late]
