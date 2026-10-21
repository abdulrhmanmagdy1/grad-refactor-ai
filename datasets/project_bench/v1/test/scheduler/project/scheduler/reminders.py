"""Reminders sent to organizers shortly before their meetings."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from scheduler import bookings

log = logging.getLogger(__name__)

DEFAULT_LEAD = timedelta(minutes=10)


@dataclass
class Reminder:
    """A message for ``recipient`` about one booking, to be sent at ``send_at``."""

    booking_id: int
    recipient: str
    send_at: datetime
    sent: bool = False


def reminders_for(booking: bookings.Booking, lead: timedelta = DEFAULT_LEAD) -> list[Reminder]:
    """Return the reminders of a booking: one for the organizer, ``lead`` before it starts.

    A cancelled booking gets none.
    """
    if booking.status is not bookings.Status.ACTIVE:
        return []
    return [Reminder(booking.booking_id, booking.organizer, booking.interval.start - lead)]


def reminder_text(booking: bookings.Booking) -> str:
    """Return the message for a booking: its title, room and start."""
    start = booking.interval.start
    return f"{booking.title} in room {booking.room_id} at {start:%H:%M} on {start:%Y-%m-%d}"


def send_due(
    calendar: bookings.Calendar, now: datetime, notify: Callable[[str, str], None]
) -> list[Reminder]:
    """Send every reminder that is due at ``now`` and not sent yet, earliest first.

    ``notify(recipient, text)`` delivers one message. When it fails, the failure is
    logged with the booking id and raised again; the reminders sent before it stay
    marked as sent and the failed one is tried again on the next run.
    """
    sent: list[Reminder] = []
    for reminder in calendar.pending_reminders(now):
        text = reminder_text(calendar.get(reminder.booking_id))
        try:
            notify(reminder.recipient, text)
        except Exception:
            log.exception("could not send the reminder for booking %s", reminder.booking_id)
            raise
        reminder.sent = True
        sent.append(reminder)
    return sent
