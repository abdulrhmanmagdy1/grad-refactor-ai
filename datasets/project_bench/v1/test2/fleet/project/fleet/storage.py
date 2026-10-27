"""Saving the fleet to disk and keeping scanned fuel receipts."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from datetime import date
from pathlib import Path

from fleet.models import Driver, Fleet, Vehicle

logger = logging.getLogger(__name__)

RECEIPT_SUFFIXES = frozenset({".pdf", ".jpg", ".jpeg", ".png"})


def receipt_path(root: Path, entry_id: int, filename: str) -> Path:
    """Where the receipt for fuel entry ``entry_id`` is kept.

    Receipts live in ``root/receipts/<entry_id>/`` under the name the driver
    uploaded them with. Only PDF and image files are accepted.
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in RECEIPT_SUFFIXES:
        raise ValueError(f"receipts must be one of {sorted(RECEIPT_SUFFIXES)}")
    return root / "receipts" / str(entry_id) / filename


def save_receipt(root: Path, entry_id: int, filename: str, content: bytes) -> Path:
    """Store an uploaded receipt and return the path it was written to."""
    path = receipt_path(root, entry_id, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def receipt_fingerprint(content: bytes) -> str:
    """A short fingerprint used to notice the same receipt uploaded twice."""
    return hashlib.md5(content, usedforsecurity=False).hexdigest()


def save_fleet(fleet: Fleet, path: Path) -> None:
    """Write vehicles and drivers to ``path`` as JSON."""
    data = {
        "vehicles": [asdict(v) for v in fleet.vehicles.values()],
        "drivers": [asdict(d) for d in fleet.drivers.values()],
    }
    path.write_text(json.dumps(data, default=date.isoformat, indent=2), encoding="utf-8")


def _vehicle_from(raw: dict) -> Vehicle:
    return Vehicle(
        vehicle_id=raw["vehicle_id"],
        make=raw["make"],
        model=raw["model"],
        year=int(raw["year"]),
        in_service_since=date.fromisoformat(raw["in_service_since"]),
        odometer_km=float(raw["odometer_km"]),
        active=bool(raw["active"]),
    )


def _driver_from(raw: dict) -> Driver:
    return Driver(
        driver_id=raw["driver_id"],
        name=raw["name"],
        license_number=raw["license_number"],
        license_expires=date.fromisoformat(raw["license_expires"]),
    )


def load_fleet(path: Path) -> Fleet:
    """Read a fleet written by :func:`save_fleet`."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        fleet = Fleet()
        for item in raw["vehicles"]:
            fleet.add_vehicle(_vehicle_from(item))
        for item in raw["drivers"]:
            fleet.add_driver(_driver_from(item))
    except Exception:
        logger.exception("could not load the fleet from %s", path)
        raise
    return fleet
