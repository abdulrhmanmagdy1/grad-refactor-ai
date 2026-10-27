"""Personal trainer sessions: booking, cancelling and charging."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from gym.billing import Ledger

LATE_CANCEL_NOTICE = timedelta(hours=24)


class TrainerError(Exception):
    """Raised when a trainer session cannot be booked or changed."""


@dataclass(frozen=True)
class Trainer:
    """A personal trainer and the fee for one session."""

    trainer_id: str
    name: str
    session_fee: Decimal


@dataclass
class Session:
    """A one-to-one session between a trainer and a member."""

    session_id: str
    trainer_id: str
    member_id: str
    starts_at: datetime
    minutes: int
    status: str = "booked"

    @property
    def ends_at(self) -> datetime:
        """The moment the session ends."""
        return self.starts_at + timedelta(minutes=self.minutes)


class TrainerDiary:
    """Books one-to-one sessions and charges them to the member's ledger.

    A trainer never has two booked sessions that overlap; a session may start at
    the minute the previous one ends. A completed session is charged its fee, and
    so is a session cancelled less than 24 hours before it starts.
    """

    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger
        self.trainers: dict[str, Trainer] = {}
        self.sessions: dict[str, Session] = {}

    def add_trainer(self, trainer: Trainer) -> None:
        """Register a trainer."""
        self.trainers[trainer.trainer_id] = trainer

    def book(self, trainer_id: str, member_id: str, starts_at: datetime, minutes: int) -> Session:
        """Book a session if the trainer is free for the whole of it."""
        if trainer_id not in self.trainers:
            raise TrainerError(f"unknown trainer {trainer_id}")
        if minutes <= 0:
            raise TrainerError("a session needs a positive length")
        ends_at = starts_at + timedelta(minutes=minutes)
        for other in self.sessions.values():
            if other.trainer_id != trainer_id or other.status != "booked":
                continue
            if other.starts_at < ends_at and starts_at < other.ends_at:
                raise TrainerError(f"{trainer_id} is busy at {starts_at:%Y-%m-%d %H:%M}")
        session_id = f"PT{len(self.sessions) + 1:04d}"
        session = Session(session_id, trainer_id, member_id, starts_at, minutes)
        self.sessions[session_id] = session
        return session

    def complete(self, session_id: str) -> Session:
        """Mark a booked session as done and charge its fee."""
        session = self._booked(session_id)
        session.status = "completed"
        self._charge(session, "personal training")
        return session

    def cancel(self, session_id: str, now: datetime) -> bool:
        """Cancel a booked session; returns True when a late-cancellation fee was charged."""
        session = self._booked(session_id)
        session.status = "cancelled"
        if session.starts_at - now < LATE_CANCEL_NOTICE:
            self._charge(session, "late cancellation")
            return True
        return False

    def sessions_in_month(self, year: int, month: int) -> list[Session]:
        """Sessions that start in the given month, earliest first."""
        found = [
            s
            for s in self.sessions.values()
            if (s.starts_at.year, s.starts_at.month) == (year, month)
        ]
        return sorted(found, key=lambda s: s.starts_at)

    def _booked(self, session_id: str) -> Session:
        session = self.sessions.get(session_id)
        if session is None or session.status != "booked":
            raise TrainerError(f"{session_id} is not a booked session")
        return session

    def _charge(self, session: Session, reason: str) -> None:
        fee = self.trainers[session.trainer_id].session_fee
        self.ledger.charge(session.member_id, fee, f"{reason} {session.starts_at:%Y-%m-%d %H:%M}")
