from datetime import date, datetime, timedelta

from scheduler.bookings import Calendar
from scheduler.export import export_room_calendar, render_agenda
from scheduler.finder import find_room, free_slots
from scheduler.rooms import Room, RoomDirectory
from scheduler.timeutil import Interval

DAY = date(2024, 6, 11)


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(DAY.year, DAY.month, DAY.day, hour, minute)


def rooms() -> RoomDirectory:
    return RoomDirectory(
        [
            Room("atlas", "Atlas", 12, frozenset({"projector", "video"})),
            Room("borneo", "Borneo", 4, frozenset({"projector"})),
            Room("crete", "Crete", 6),
        ]
    )


def test_suitable_rooms_are_smallest_first():
    directory = rooms()
    assert [r.room_id for r in directory.suitable(4, {"projector"})] == ["borneo", "atlas"]
    assert [r.room_id for r in directory.suitable(10)] == ["atlas"]


def test_free_slots_leave_out_booked_time():
    calendar = Calendar()
    calendar.book("crete", "ana", "Planning", Interval(at(9), at(12)))
    slots = free_slots(calendar, "crete", DAY, timedelta(hours=1))
    starts = [slot.start for slot in slots]
    assert at(10) not in starts
    assert at(13) in starts
    assert starts[-1] == at(17)


def test_find_room_skips_a_booked_room():
    calendar = Calendar()
    calendar.book("borneo", "ana", "Planning", Interval(at(10), at(11)))
    room = find_room(rooms(), calendar, Interval(at(10, 30), at(11, 30)), 3, {"projector"})
    assert room is not None
    assert room.room_id == "atlas"


def test_export_writes_an_ics_file(tmp_path):
    calendar = Calendar()
    calendar.book("atlas", "ana", "Planning, Q3", Interval(at(9), at(10)))
    path = export_room_calendar(calendar, rooms().get("atlas"), tmp_path, "atlas-june")
    assert path.resolve() == (tmp_path / "atlas-june.ics").resolve()
    text = path.read_bytes().decode("utf-8")
    assert text.startswith("BEGIN:VCALENDAR\r\n")
    assert "SUMMARY:Planning\\, Q3\r\n" in text
    assert "DTSTART:20240611T090000\r\n" in text


def test_agenda_lists_meetings_gaps_and_free_rooms():
    calendar = Calendar()
    calendar.book("atlas", "ana", "Planning", Interval(at(9), at(10)))
    calendar.book("atlas", "ben", "Review", Interval(at(11), at(12, 30)))
    calendar.book("crete", "ana", "1:1", Interval(at(15), at(15, 30)))
    agenda = render_agenda(calendar, rooms(), DAY)
    assert "  09:00-10:00  Planning (ana)" in agenda
    assert "    free 10:00-11:00 (60 min)" in agenda
    assert "Free all day: Borneo" in agenda
    assert "Total: 3 meeting(s), 3.00 h booked" in agenda
    assert "Busiest room: Atlas (2.50 h)" in agenda
    assert "Most meetings organized by: ana (2)" in agenda
