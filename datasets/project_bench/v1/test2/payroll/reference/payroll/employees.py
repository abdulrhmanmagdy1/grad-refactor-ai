"""Employee records, kept in a SQLite database."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum


class PayType(Enum):
    """How an employee is paid."""

    HOURLY = "hourly"
    SALARIED = "salaried"


@dataclass(frozen=True)
class Employee:
    """One employee. `rate` is the hourly rate or, for salaried staff, the monthly salary."""

    employee_id: str
    name: str
    department: str
    pay_type: PayType
    rate: Decimal
    start_date: date


_SCHEMA = """
CREATE TABLE IF NOT EXISTS employees (
    employee_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    department TEXT NOT NULL,
    pay_type TEXT NOT NULL,
    rate TEXT NOT NULL,
    start_date TEXT NOT NULL
)
"""


def _to_employee(row: sqlite3.Row) -> Employee:
    """Turn a database row back into an Employee."""
    return Employee(
        employee_id=row["employee_id"],
        name=row["name"],
        department=row["department"],
        pay_type=PayType(row["pay_type"]),
        rate=Decimal(row["rate"]),
        start_date=date.fromisoformat(row["start_date"]),
    )


class EmployeeStore:
    """Employee records. The department filter is typed in by HR staff on the web form."""

    def __init__(self, database: str = ":memory:") -> None:
        self._conn = sqlite3.connect(database)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_SCHEMA)

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def add(self, employee: Employee) -> None:
        """Insert a new employee; ids are unique and rates must be positive."""
        if employee.rate <= 0:
            raise ValueError("the rate must be positive")
        with self._conn:
            self._conn.execute(
                "INSERT INTO employees"
                " (employee_id, name, department, pay_type, rate, start_date)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    employee.employee_id,
                    employee.name,
                    employee.department,
                    employee.pay_type.value,
                    str(employee.rate),
                    employee.start_date.isoformat(),
                ),
            )

    def get(self, employee_id: str) -> Employee:
        """Return one employee, or raise KeyError."""
        row = self._conn.execute(
            "SELECT * FROM employees WHERE employee_id = ?", (employee_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"no employee {employee_id}")
        return _to_employee(row)

    def many(self, employee_ids: Iterable[str]) -> list[Employee]:
        """Return the employees with these ids, ordered by id; unknown ids are skipped."""
        ids = list(employee_ids)
        if not ids:
            return []
        placeholders = ", ".join("?" for _ in ids)
        query = f"SELECT * FROM employees WHERE employee_id IN ({placeholders})"
        rows = self._conn.execute(query + " ORDER BY employee_id", ids).fetchall()
        return [_to_employee(row) for row in rows]

    def by_department(self, department: str) -> list[Employee]:
        """Return the employees of one department, ordered by id."""
        rows = self._conn.execute(
            "SELECT * FROM employees WHERE department = ? ORDER BY employee_id", (department,)
        ).fetchall()
        return [_to_employee(row) for row in rows]

    def all(self) -> list[Employee]:
        """Return every employee, ordered by id."""
        rows = self._conn.execute("SELECT * FROM employees ORDER BY employee_id").fetchall()
        return [_to_employee(row) for row in rows]
