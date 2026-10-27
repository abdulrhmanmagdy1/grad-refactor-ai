"""The monthly payroll report and the bank transfer file."""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from payroll.employees import Employee
from payroll.money import ZERO
from payroll.payslips import Payslip
from payroll.timesheets import Timesheet

WEEKLY_HOURS = Decimal(40)


@dataclass(frozen=True)
class DepartmentTotal:
    """Totals of one department's payslips."""

    department: str
    headcount: int
    gross: Decimal
    deductions: Decimal
    net: Decimal


def department_totals(payslips: Iterable[Payslip]) -> list[DepartmentTotal]:
    """Headcount and money totals per department, sorted by department name.

    Each department's totals cover only that department's payslips.
    """
    ordered = sorted(payslips, key=lambda slip: (slip.department, slip.employee_id))
    totals: list[DepartmentTotal] = []
    current: str | None = None
    headcount = 0
    gross = deductions = net = ZERO
    for slip in ordered:
        if slip.department != current:
            if current is not None:
                totals.append(DepartmentTotal(current, headcount, gross, deductions, net))
            current = slip.department
            headcount = 0
        headcount += 1
        gross += slip.gross
        deductions += slip.deductions
        net += slip.net
    if current is not None:
        totals.append(DepartmentTotal(current, headcount, gross, deductions, net))
    return totals


def overtime_by_department(
    employees: Iterable[Employee], timesheets: Iterable[Timesheet]
) -> dict[str, Decimal]:
    """Overtime hours of the month per department (hours above 40 in an ISO week)."""
    department_of = {employee.employee_id: employee.department for employee in employees}
    result: dict[str, Decimal] = {}
    for sheet in timesheets:
        department = department_of[sheet.employee_id]
        extra = Decimal(0)
        for hours in sheet.hours_by_week().values():
            if hours > WEEKLY_HOURS:
                extra += hours - WEEKLY_HOURS
        result[department] = result.get(department, Decimal(0)) + extra
    return result


def _payslip_block(slip: Payslip) -> list[str]:
    """The lines of one employee in the monthly report."""
    lines = [f"Payslip {slip.period}: {slip.name} ({slip.employee_id})"]
    if slip.regular_hours or slip.overtime_hours:
        lines.append(f"  Hours: {slip.regular_hours} regular, {slip.overtime_hours} overtime")
    lines.append(f"  {'Gross pay':<20}{slip.gross:>12}")
    lines.append(f"  {'Pension':<20}{-slip.pension:>12}")
    lines.append(f"  {'Income tax':<20}{-slip.income_tax:>12}")
    lines.append(f"  {'Health insurance':<20}{-slip.health_insurance:>12}")
    lines.append(f"  {'Net pay':<20}{slip.net:>12}")
    return lines


def render_monthly_report(
    period: str,
    payslips: Sequence[Payslip],
    overtime: dict[str, Decimal] | None = None,
) -> str:
    """The monthly payroll report: every payslip, department totals and grand totals."""
    lines: list[str] = []
    title = f"Payroll report {period}"
    lines.append(title)
    lines.append("=" * len(title))
    lines.append("")
    wrong_period = [slip.employee_id for slip in payslips if slip.period != period]
    if wrong_period:
        raise ValueError(f"payslips from another period: {', '.join(wrong_period)}")
    if not payslips:
        lines.append("No payslips this month.")
        return "\n".join(lines) + "\n"
    lines.append("Employees")
    lines.append("---------")
    for slip in sorted(payslips, key=lambda item: item.employee_id):
        lines.extend(_payslip_block(slip))
        lines.append("")
    lines.append("Departments")
    lines.append("-----------")
    header = f"{'Department':<16}{'Staff':>6}{'Gross':>14}{'Deductions':>14}{'Net':>14}"
    lines.append(header)
    for total in department_totals(payslips):
        row = (
            f"{total.department:<16}{total.headcount:>6}"
            f"{total.gross:>14}{total.deductions:>14}{total.net:>14}"
        )
        lines.append(row)
    lines.append("")
    gross = sum((slip.gross for slip in payslips), ZERO)
    pension = sum((slip.pension for slip in payslips), ZERO)
    tax = sum((slip.income_tax for slip in payslips), ZERO)
    health = sum((slip.health_insurance for slip in payslips), ZERO)
    net = sum((slip.net for slip in payslips), ZERO)
    lines.append("Totals")
    lines.append("------")
    lines.append(f"{'Employees':<20}{len(payslips):>14}")
    lines.append(f"{'Gross pay':<20}{gross:>14}")
    lines.append(f"{'Pension':<20}{pension:>14}")
    lines.append(f"{'Income tax':<20}{tax:>14}")
    lines.append(f"{'Health insurance':<20}{health:>14}")
    lines.append(f"{'Net pay':<20}{net:>14}")
    if overtime:
        lines.append("")
        lines.append("Overtime hours")
        lines.append("--------------")
        for department in sorted(overtime):
            hours = overtime[department]
            if hours > 0:
                lines.append(f"{department:<20}{hours:>14}")
        total_overtime = sum(overtime.values(), Decimal(0))
        lines.append(f"{'All departments':<20}{total_overtime:>14}")
    zero_pay = [slip.employee_id for slip in payslips if slip.gross == 0]
    if zero_pay:
        lines.append("")
        lines.append(f"No pay this month: {', '.join(sorted(zero_pay))}")
    return "\n".join(lines) + "\n"


def write_bank_file(payslips: Iterable[Payslip], path: Path) -> str:
    """Write the bank transfer file (employee id, name, net pay) and return its checksum.

    The bank's upload form asks for the MD5 hex digest of the file to detect damaged
    uploads.
    """
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["employee_id", "name", "net"])
        for slip in sorted(payslips, key=lambda item: item.employee_id):
            writer.writerow([slip.employee_id, slip.name, str(slip.net)])
    return hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest()
