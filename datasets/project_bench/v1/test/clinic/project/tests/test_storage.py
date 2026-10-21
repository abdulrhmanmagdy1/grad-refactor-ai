from datetime import date

import pytest

from clinic.models import Patient
from clinic.storage import PatientStore


def test_add_and_get_patient():
    store = PatientStore()
    saved = store.add_patient(Patient("  Mona Hassan ", date(1990, 5, 17), "0100 555 0101"))
    assert saved.id is not None
    assert store.get_patient(saved.id) == Patient(
        "Mona Hassan", date(1990, 5, 17), "0100 555 0101", saved.id
    )
    assert store.count_patients() == 1


def test_unknown_patient():
    with pytest.raises(KeyError):
        PatientStore().get_patient(42)


def test_a_patient_needs_a_name():
    store = PatientStore()
    with pytest.raises(ValueError):
        store.add_patient(Patient("   ", date(2001, 1, 1)))
    assert store.count_patients() == 0


def test_patients_by_ids():
    store = PatientStore()
    first, _, third = store.add_patients(
        [
            Patient("Amal", date(1980, 2, 2)),
            Patient("Basem", date(1985, 3, 3)),
            Patient("Dina", date(1999, 4, 4)),
        ]
    )
    found = store.patients_by_ids([third.id, first.id, 999])
    assert [patient.name for patient in found] == ["Amal", "Dina"]
    assert store.patients_by_ids([]) == []
