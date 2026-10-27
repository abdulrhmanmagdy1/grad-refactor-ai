"""Monthly payslips."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from payroll.employees import Employee, PayType
from payroll.money import ZERO, prorate, to_cents
from payroll.tax import health_insurance, income_tax, pension_contribution
from payroll.timesheets import OVERTIME_MULTIPLIER, Timesheet, split_overtime


@dataclass(frozen=True)
class Payslip:
    """One employee's pay for one month. Net pay is gross pay minus every deduction."""

    employee_id: str
    name: str
    department: str
    period: str
    regular_hours: Decimal
    overtime_hours: Decimal
    gross: Decimal
    pension: Decimal
    income_tax: Decimal
    health_insurance: Decimal

    @property
    def deductions(self) -> Decimal:
        """Sum of every deduction."""
        return self.pension + self.income_tax + self.health_insurance

    @property
    def net(self) -> Decimal:
        """What is paid into the employee's account."""
        return self.gross - self.deductions

    def render_text(self) -> str:
        """Plain-text payslip handed to the employee."""
        lines = [f"Payslip {self.period}: {self.name} ({self.employee_id})"]
        if self.regular_hours or self.overtime_hours:
            lines.append(f"  Hours: {self.regular_hours} regular, {self.overtime_hours} overtime")
        lines.append(f"  {'Gross pay':<20}{self.gross:>12}")
        lines.append(f"  {'Pension':<20}{-self.pension:>12}")
        lines.append(f"  {'Income tax':<20}{-self.income_tax:>12}")
        lines.append(f"  {'Health insurance':<20}{-self.health_insurance:>12}")
        lines.append(f"  {'Net pay':<20}{self.net:>12}")
        return "\n".join(lines) + "\n"


def days_employed(start_date: date, year: int, month: int) -> int:
    """Days of the month on which the employee was employed, start day included."""
    last_day = calendar.monthrange(year, month)[1]
    first = date(year, month, 1)
    if start_date > date(year, month, last_day):
        return 0
    if start_date <= first:
        return last_day
    return last_day - start_date.day + 1


def gross_pay(
    employee: Employee, timesheet: Timesheet | None, year: int, month: int
) -> tuple[Decimal, Decimal, Decimal]:
    """Return (regular hours, overtime hours, gross pay) for the month.

    Hourly staff are paid their hours, overtime at 1.5 times the rate. Salaried staff
    get the monthly salary, prorated by calendar days when they started this month.
    """
    if employee.pay_type is PayType.HOURLY:
        if timesheet is None:
            return Decimal(0), Decimal(0), ZERO
        regular, overtime = split_overtime(timesheet)
        pay = regular * employee.rate + overtime * employee.rate * OVERTIME_MULTIPLIER
        return regular, overtime, to_cents(pay)
    days_in_month = calendar.monthrange(year, month)[1]
    worked = days_employed(employee.start_date, year, month)
    if worked == 0:
        return Decimal(0), Decimal(0), ZERO
    salary = prorate(employee.rate, worked, days_in_month)
    return Decimal(0), Decimal(0), to_cents(salary)


def build_payslip(
    employee: Employee, timesheet: Timesheet | None, year: int, month: int
) -> Payslip:
    """Compute the payslip of one employee for one month.

    Pension is taken from gross pay; income tax is due on gross pay minus pension.
    """
    if timesheet is not None and timesheet.employee_id != employee.employee_id:
        raise ValueError("the timesheet belongs to another employee")
    regular, overtime, gross = gross_pay(employee, timesheet, year, month)
    pension = pension_contribution(gross)
    return Payslip(
        employee_id=employee.employee_id,
        name=employee.name,
        department=employee.department,
        period=f"{year}-{month:02d}",
        regular_hours=regular,
        overtime_hours=overtime,
        gross=gross,
        pension=pension,
        income_tax=income_tax(gross - pension),
        health_insurance=health_insurance(gross),
    )
