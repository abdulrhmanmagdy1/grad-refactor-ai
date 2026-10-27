"""CSV contact import through an import folder."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path

from crm.contacts import ContactBook

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ("name", "email")


@dataclass
class ImportResult:
    """What an import did: counts and the rows it skipped, by CSV line number."""

    created: int = 0
    merged: int = 0
    companies: int = 0
    skipped: list[tuple[int, str]] = field(default_factory=list)


class CsvImporter:
    """Keeps uploaded CSV files in one import folder and imports them."""

    def __init__(self, import_dir: Path) -> None:
        self.import_dir = import_dir
        self.import_dir.mkdir(parents=True, exist_ok=True)

    def save_upload(self, filename: str, data: bytes) -> Path:
        """Store an uploaded file inside the import folder and return its path."""
        root = self.import_dir.resolve()
        target = (root / filename).resolve()
        if target.parent != root:
            raise ValueError(f"invalid upload name {filename!r}")
        target.write_bytes(data)
        return target

    def pending(self) -> list[str]:
        """Return the names of the CSV files waiting in the import folder."""
        return sorted(p.name for p in self.import_dir.glob("*.csv"))

    def _read_rows(self, path: Path) -> list[dict[str, str]]:
        """Return the rows of a CSV file; log and re-raise if it cannot be read."""
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                return list(csv.DictReader(handle))
        except Exception:
            logger.exception("could not read import file %s", path)
            raise

    def import_contacts(self, path: Path, book: ContactBook) -> ImportResult:
        """Import contacts from a saved upload into ``book``.

        Required columns are ``name`` and ``email``; ``company``, ``phone``
        and ``tags`` (separated by ``;``) are optional. Rows without a name
        or with an address lacking ``@`` are skipped and reported with their
        line number (the header is line 1). Companies are created the first
        time their name appears. A row whose email is already known merges
        into the existing contact.
        """
        rows = self._read_rows(path)
        result = ImportResult()
        if rows:
            missing = [c for c in REQUIRED_COLUMNS if c not in rows[0]]
            if missing:
                raise ValueError(f"missing columns: {', '.join(missing)}")
        for line_no, row in enumerate(rows, start=2):
            name = (row.get("name") or "").strip()
            email = (row.get("email") or "").strip()
            if not name:
                result.skipped.append((line_no, "missing name"))
                continue
            if "@" not in email:
                result.skipped.append((line_no, f"invalid email {email!r}"))
                continue
            company_id = None
            company_name = (row.get("company") or "").strip()
            if company_name:
                company = book.company_named(company_name)
                if company is None:
                    domain = email.rpartition("@")[2].lower()
                    company = book.add_company(company_name, domain)
                    result.companies += 1
                company_id = company.company_id
            tags = []
            for raw in (row.get("tags") or "").split(";"):
                tag = raw.strip().lower()
                if tag and tag not in tags:
                    tags.append(tag)
            phone = "".join(ch for ch in (row.get("phone") or "") if ch.isdigit() or ch == "+")
            known = book.find_by_email(email) is not None
            contact = book.add_contact(name, email, company_id, tags)
            if phone and not contact.phone:
                contact.phone = phone
            if known:
                result.merged += 1
            else:
                result.created += 1
        logger.info(
            "imported %s: %d created, %d merged, %d skipped",
            path.name,
            result.created,
            result.merged,
            len(result.skipped),
        )
        return result
