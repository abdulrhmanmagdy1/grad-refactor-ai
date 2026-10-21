"""Records of the garage: spaces, tickets and permits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class Space:
    """One parking space; `kind` is "standard", "compact", "ev" or "accessible"."""

    level: int
    number: int
    kind: str = "standard"
    plate: str | None = None

    @property
    def code(self) -> str:
        """The label painted on the floor, for example "L2-014"."""
        return f"L{self.level}-{self.number:03d}"

    @property
    def is_free(self) -> bool:
        return self.plate is None


@dataclass
class Ticket:
    """A stay in the garage; `amount` is set when the car leaves."""

    ticket_id: str
    plate: str
    space: str
    entered: datetime
    exited: datetime | None = None
    amount: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.exited is None

    @property
    def level(self) -> str:
        """The level part of the space code, for example "L2"."""
        return self.space.split("-")[0]


@dataclass
class Permit:
    """A monthly permit, valid from `start` up to the day before `expires`."""

    plate: str
    holder: str
    start: date
    expires: date
    price: float
