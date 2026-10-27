from datetime import date, timedelta
from decimal import Decimal

import pytest

from payroll.employees import Employee, EmployeeStore, PayType
from payroll.money import parse_amount, prorate, to_cents
from payroll.payslips import build_payslip, days_employed
from payroll.report import render_monthly_report, write_bank_file
from payroll.tax import income_tax, pension_contribution
from payroll.timesheets import Timesheet, split_overtime

ADA = Employee("E001", "Ada", "Engineering", PayType.HOURLY, Decimal("20.00"), date(2024, 5, 1))
BOB = Employee("E002", "Bob", "Engineering", PayType.SALARIED, Decimal("4000.00"), date(2025, 1, 10))


def april_timesheet() -> Timesheet:
    sheet = Timesheet("E001", 2026, 4)
    for offset in range(5):
        sheet.add(date(2026, 4, 6) + timedelta(days=offset), Decimal(9))
        sheet.add(date(2026, 4, 13) + timedelta(days=offset), Decimal(8))
    return sheet


def test_money_helpers():
    assert to_cents(Decimal("2.344")) == Decimal("2.34")
    assert to_cents(Decimal("2.346")) == Decimal("2.35")
    assert prorate(Decimal("3000"), 10, 30) == Decimal("1000")
    assert parse_amount("1,250.50") == Decimal("1250.50")
    with pytest.raises(ValueError):
        prorate(Decimal("1"), 1, 0)


def test_timesheet_rejects_other_months_and_long_days():
    sheet = Timesheet("E001", 2026, 4)
    with pytest.raises(ValueError):
        sheet.add(date(2026, 5, 1), Decimal(8))
    sheet.add(date(2026, 4, 1), Decimal(20))
    with pytest.raises(ValueError):
        sheet.add(date(2026, 4, 1), Decimal(5))


def test_overtime_is_counted_per_week():
    assert split_overtime(april_timesheet()) == (Decimal(80), Decimal(5))


def test_tax_and_pension():
    assert income_tax(Decimal("500")) == Decimal("0.00")
    assert income_tax(Decimal("7000")) == Decimal("1100.00")
    assert pension_contribution(Decimal("10000")) == Decimal("400.00")


def test_hourly_payslip():
    slip = build_payslip(ADA, april_timesheet(), 2026, 4)
    assert slip.gross == Decimal("1750.00")
    assert slip.pension == Decimal("87.50")
    assert slip.income_tax == Decimal("66.25")
    assert slip.net == Decimal("1571.25")
    assert "Net pay" in slip.render_text()


def test_salaried_payslip_for_a_full_month():
    slip = build_payslip(BOB, None, 2026, 4)
    assert slip.gross == Decimal("4000.00")
    assert slip.income_tax == Decimal("360.00")
    assert slip.net == Decimal("3415.00")


def test_days_employed():
    assert days_employed(date(2026, 4, 1), 2026, 4) == 30
    assert days_employed(date(2026, 5, 2), 2026, 4) == 0


def test_store_round_trip():
    store = EmployeeStore()
    store.add(ADA)
    store.add(BOB)
    assert store.get("E002") == BOB
    assert [e.employee_id for e in store.many(["E002", "E009", "E001"])] == ["E001", "E002"]
    assert store.by_department("Engineering") == [ADA, BOB]
    with pytest.raises(KeyError):
        store.get("E404")
    store.close()


def test_monthly_report_and_bank_file(tmp_path):
    slips = [build_payslip(ADA, april_timesheet(), 2026, 4), build_payslip(BOB, None, 2026, 4)]
    report = render_monthly_report("2026-04", slips, {"Engineering": Decimal(5)})
    assert "Engineering" in report
    assert "4986.25" in report
    checksum = write_bank_file(slips, tmp_path / "bank.csv")
    assert len(checksum) == 32
    assert (tmp_path / "bank.csv").read_text(encoding="utf-8").splitlines()[1] == "E001,Ada,1571.25"
