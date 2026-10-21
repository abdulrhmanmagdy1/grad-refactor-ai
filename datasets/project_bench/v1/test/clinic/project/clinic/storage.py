"""SQLite storage for patient records."""

from __future__ import annotations

import dataclasses
import logging
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import date

from clinic.models import Patient

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    birth_date TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT ''
)
"""


class PatientStore:
    """Patient records in an SQLite database (a file path, or ':memory:')."""

    def __init__(self, database: str = ":memory:") -> None:
        self._conn = sqlite3.connect(database)
        self._conn.execute(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a block of writes as one unit.

        The block is committed when it finishes; when it raises, everything it wrote
        is rolled back and the exception propagates to the caller.
        """
        try:
            yield self._conn
        except Exception:
            logger.exception("patient transaction failed, rolling back")
            self._conn.rollback()
            raise
        self._conn.commit()

    def add_patient(self, patient: Patient) -> Patient:
        """Store a new patient and return a copy that carries its id."""
        with self.transaction():
            return self._insert(patient)

    def add_patients(self, patients: Iterable[Patient]) -> list[Patient]:
        """Store several patients together; if one of them is invalid, none is stored."""
        with self.transaction():
            return [self._insert(patient) for patient in patients]

    def _insert(self, patient: Patient) -> Patient:
        name = patient.name.strip()
        if not name:
            raise ValueError("a patient needs a name")
        cursor = self._conn.execute(
            "INSERT INTO patients (name, birth_date, phone) VALUES (?, ?, ?)",
            (name, patient.birth_date.isoformat(), patient.phone),
        )
        return dataclasses.replace(patient, name=name, id=cursor.lastrowid)

    def get_patient(self, patient_id: int) -> Patient:
        """Return the patient with ``patient_id``; KeyError when there is none."""
        row = self._conn.execute(
            "SELECT id, name, birth_date, phone FROM patients WHERE id = ?", (patient_id,)
        ).fetchone()
        if row is None:
            raise KeyError(patient_id)
        return _to_patient(row)

    def patients_by_ids(self, patient_ids: Sequence[int]) -> list[Patient]:
        """Return the patients with the given ids, ordered by id; unknown ids are skipped."""
        if not patient_ids:
            return []
        placeholders = ", ".join("?" for _ in patient_ids)
        query = (
            "SELECT id, name, birth_date, phone FROM patients "
            f"WHERE id IN ({placeholders}) ORDER BY id"
        )
        rows = self._conn.execute(query, tuple(patient_ids)).fetchall()
        return [_to_patient(row) for row in rows]

    def search_patients(self, name_part: str) -> list[Patient]:
        """Return the patients whose name contains ``name_part``, ignoring case, by name."""
        query = (
            "SELECT id, name, birth_date, phone FROM patients "
            f"WHERE name LIKE '%{name_part}%' ORDER BY name"
        )
        rows = self._conn.execute(query).fetchall()
        return [_to_patient(row) for row in rows]

    def count_patients(self) -> int:
        """Number of stored patients."""
        (count,) = self._conn.execute("SELECT COUNT(*) FROM patients").fetchone()
        return int(count)


def _to_patient(row: tuple[int, str, str, str]) -> Patient:
    """Build a Patient from a (id, name, birth_date, phone) row."""
    patient_id, name, birth_date, phone = row
    return Patient(name=name, birth_date=date.fromisoformat(birth_date), phone=phone, id=patient_id)
