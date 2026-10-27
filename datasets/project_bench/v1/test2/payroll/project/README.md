# payroll

Monthly payroll for a small company.

- `payroll.money`: Decimal helpers; amounts are rounded to cents with halves rounding up.
- `payroll.employees`: employee records in SQLite (hourly or salaried).
- `payroll.timesheets`: hours per day and the overtime rule (above 40 hours in an ISO
  week, paid at 1.5 times the hourly rate).
- `payroll.tax`: monthly progressive income tax, pension (5% of gross, capped at 400.00)
  and flat health insurance.
- `payroll.payslips`: gross pay, deductions and net pay per employee. Salaried staff who
  join during a month get the share of the salary for the calendar days they were
  employed.
- `payroll.report`: the monthly report with department totals and the bank transfer file.

Run the tests with `pytest`.
