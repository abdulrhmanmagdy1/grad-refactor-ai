"""Records kept by the CRM."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass
class Company:
    """An organisation we sell to, identified by its email domain."""

    company_id: str
    name: str
    domain: str = ""


@dataclass
class Contact:
    """A person, unique by email address."""

    contact_id: str
    name: str
    email: str
    company_id: str | None = None
    phone: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class Deal:
    """A sales opportunity moving through the pipeline stages."""

    deal_id: str
    title: str
    company_id: str
    amount: Decimal
    expected_close: date
    stage: str = "lead"


@dataclass(frozen=True)
class StageChange:
    """One move of a deal from one stage to another."""

    deal_id: str
    from_stage: str
    to_stage: str
    at: datetime


@dataclass
class Activity:
    """A call, email or meeting planned with a contact."""

    activity_id: str
    contact_id: str
    kind: str
    due: datetime
    note: str = ""
    done: bool = False
