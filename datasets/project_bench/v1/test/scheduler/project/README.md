# scheduler

Room booking for an office: rooms and their equipment, bookings with conflict detection,
recurring meetings, reminders for organizers, iCalendar export and a printable agenda.

- A booking holds its room from its start up to its end; the end itself is free, so
  back-to-back meetings may share a room.
- Bookings lie between 08:00 and 18:00 on one day and start and end on a quarter hour.
- Each `Calendar` has its own office holidays; nothing can be booked on them.
- A recurring series is booked as a whole or not at all, by the organizer who asked for
  it and under its title.
- Organizers get a reminder ten minutes before each meeting.
- Room calendars are exported to `.ics` files in a chosen export folder.

Run the tests with `pytest`.
