import hashlib
from datetime import date, timedelta
from decimal import Decimal

from payroll.employees import Employee, EmployeeStore, PayType
from payroll.money import to_cents
from payroll.payslips import Payslip, build_payslip
from payroll.report import department_totals, overtime_by_department, write_bank_file
from payroll.timesheets import Timesheet

ADA = Employee("E001", "Ada", "Engineering", PayType.HOURLY, Decimal("20.00"), date(2024, 5, 1))
BOB = Employee("E002", "Bob", "Sales", PayType.SALARIED, Decimal("3000.00"), date(2026, 4, 16))
CY = Employee("E003", "Cy", "Sales", PayType.SALARIED, Decimal("4000.00"), date(2025, 1, 1))


def slip(employee_id: str, department: str, gross: str) -> Payslip:
    return Payslip(
        employee_id=employee_id,
        name=employee_id,
        department=department,
        period="2026-04",
        regular_hours=Decimal(0),
        overtime_hours=Decimal(0),
        gross=Decimal(gross),
        pension=Decimal("10.00"),
        income_tax=Decimal("20.00"),
        health_insurance=Decimal("25.00"),
    )


def test_B1_half_cents_round_up():
    assert to_cents(Decimal("2.345")) == Decimal("2.35")
    assert to_cents(Decimal("0.125")) == Decimal("0.13")
    assert to_cents(Decimal("10.005")) == Decimal("10.01")


def test_B2_salary_is_prorated_for_a_mid_month_start():
    payslip = build_payslip(BOB, None, 2026, 4)
    assert payslip.gross == Decimal("1500.00")


def test_B3_department_totals_do_not_carry_over():
    totals = department_totals(
        [slip("E001", "Engineering", "1000.00"), slip("E002", "Sales", "2000.00"),
         slip("E003", "Sales", "500.00")]
    )
    assert [t.department for t in totals] == ["Engineering", "Sales"]
    engineering, sales = totals
    assert engineering.headcount == 1
    assert engineering.gross == Decimal("1000.00")
    assert sales.headcount == 2
    assert sales.gross == Decimal("2500.00")
    assert sales.deductions == Decimal("110.00")
    assert sales.net == Decimal("2390.00")


def test_S1_department_filter_is_not_injectable():
    store = EmployeeStore()
    store.add(ADA)
    store.add(CY)
    try:
        found = store.by_department("Sales' OR '1'='1")
    except ValueError:
        found = []
    assert found == []
    assert store.by_department("Sales") == [CY]


def test_keep_lookup_by_ids_with_quoted_department():
    store = EmployeeStore()
    quoted = Employee("E010", "Dee", "R&D 'Labs'", PayType.HOURLY, Decimal("30.00"), date(2025, 1, 1))
    store.add(ADA)
    store.add(quoted)
    assert store.many(["E010", "E001"]) == [ADA, quoted]


def test_keep_full_month_salary():
    payslip = build_payslip(CY, None, 2026, 4)
    assert payslip.gross == Decimal("4000.00")
    assert payslip.net == Decimal("3415.00")


def test_keep_rounding_below_half():
    assert to_cents(Decimal("2.344")) == Decimal("2.34")
    assert to_cents(Decimal("7")) == Decimal("7.00")


def test_keep_single_department_totals():
    totals = department_totals([slip("E002", "Sales", "100.00"), slip("E001", "Sales", "200.00")])
    assert len(totals) == 1
    assert totals[0].headcount == 2
    assert totals[0].gross == Decimal("300.00")


def test_keep_overtime_by_department():
    sheet = Timesheet("E001", 2026, 4)
    for offset in range(5):
        sheet.add(date(2026, 4, 6) + timedelta(days=offset), Decimal(10))
    assert overtime_by_department([ADA], [sheet]) == {"Engineering": Decimal(10)}


def test_keep_bank_file_checksum_is_md5_of_the_file(tmp_path):
    path = tmp_path / "bank.csv"
    checksum = write_bank_file([slip("E001", "Engineering", "1000.00")], path)
    assert checksum == hashlib.md5(path.read_bytes()).hexdigest()
