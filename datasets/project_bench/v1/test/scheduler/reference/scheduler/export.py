"""Exports: an iCalendar file per room and a printable agenda for one day."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from scheduler.bookings import Booking, Calendar
from scheduler.rooms import Room, RoomDirectory
from scheduler.timeutil import format_span


def _ics_time(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%S")


def _ics_text(text: str) -> str:
    """Escape text for an iCalendar property value."""
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def to_ics(bookings: list[Booking], room: Room) -> str:
    """Return the bookings of one room as an iCalendar document with CRLF line ends."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//office//scheduler//EN"]
    for booking in bookings:
        lines += [
            "BEGIN:VEVENT",
            f"UID:booking-{booking.booking_id}@scheduler",
            f"DTSTART:{_ics_time(booking.interval.start)}",
            f"DTEND:{_ics_time(booking.interval.end)}",
            f"SUMMARY:{_ics_text(booking.title)}",
            f"LOCATION:{_ics_text(room.name)}",
            f"ORGANIZER;CN={_ics_text(booking.organizer)}:noreply@office.invalid",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def export_room_calendar(calendar: Calendar, room: Room, export_dir: Path, name: str) -> Path:
    """Write the room's active bookings to ``<export_dir>/<name>.ics`` and return the path.

    ``name`` is the file name, without extension, that the user typed in the export
    form.
    """
    path = export_dir / f"{name}.ics"
    if path.resolve().parent != export_dir.resolve():
        raise ValueError(f"the export name must be a plain file name: {name!r}")
    document = to_ics(calendar.bookings_for_room(room.room_id), room)
    path.write_text(document, encoding="utf-8", newline="")
    return path


def render_agenda(calendar: Calendar, directory: RoomDirectory, day: date) -> str:
    """Return the printable agenda of one day.

    Each room with meetings is listed in id order with its equipment, its meetings
    (time, title, organizer) and the free time between two meetings. Rooms without
    meetings are listed together as free all day. A summary closes the agenda: the
    number of meetings, the hours booked, the busiest room and who organizes most.
    """
    lines = [f"Agenda for {day:%A %d %B %Y}", "=" * 40]
    if calendar.is_holiday(day):
        lines.append("The office is closed.")
        return "\n".join(lines) + "\n"
    meeting_count = 0
    booked_total = timedelta()
    busiest_name = ""
    busiest_time = timedelta()
    free_rooms: list[str] = []
    organizers: Counter[str] = Counter()
    for room in directory:
        meetings = calendar.bookings_on(day, room.room_id)
        if not meetings:
            free_rooms.append(room.name)
            continue
        equipment = ", ".join(sorted(room.features)) or "no equipment"
        lines.append(f"{room.name} - seats {room.capacity}, {equipment}")
        booked = timedelta()
        previous_end = None
        for booking in meetings:
            if previous_end is not None and booking.interval.start > previous_end:
                gap_minutes = int((booking.interval.start - previous_end).total_seconds() // 60)
                lines.append(
                    f"    free {previous_end:%H:%M}-{booking.interval.start:%H:%M}"
                    f" ({gap_minutes} min)"
                )
            lines.append(
                f"  {format_span(booking.interval)}  {booking.title} ({booking.organizer})"
            )
            booked += booking.interval.duration
            organizers[booking.organizer] += 1
            previous_end = booking.interval.end
        hours = booked.total_seconds() / 3600
        lines.append(f"  {len(meetings)} meeting(s), {hours:.2f} h booked")
        lines.append("")
        meeting_count += len(meetings)
        booked_total += booked
        if booked > busiest_time:
            busiest_name = room.name
            busiest_time = booked
    if free_rooms:
        lines.append("Free all day: " + ", ".join(free_rooms))
        lines.append("")
    total_hours = booked_total.total_seconds() / 3600
    lines.append(f"Total: {meeting_count} meeting(s), {total_hours:.2f} h booked")
    if busiest_name:
        busiest_hours = busiest_time.total_seconds() / 3600
        lines.append(f"Busiest room: {busiest_name} ({busiest_hours:.2f} h)")
    if organizers:
        top, top_count = organizers.most_common(1)[0]
        lines.append(f"Most meetings organized by: {top} ({top_count})")
    return "\n".join(lines) + "\n"
