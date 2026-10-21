"""Meeting rooms and the directory that lists them."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field


class UnknownRoom(LookupError):
    """Raised when no room has the given id."""


@dataclass(frozen=True)
class Room:
    """A bookable room. ``features`` names its equipment, e.g. "projector" or "video"."""

    room_id: str
    name: str
    capacity: int
    features: frozenset[str] = field(default_factory=frozenset)

    def suits(self, attendees: int, needs: Iterable[str] = ()) -> bool:
        """Return True when the room seats ``attendees`` people and has every needed feature."""
        return attendees <= self.capacity and set(needs) <= self.features


class RoomDirectory:
    """All rooms of the office, by id."""

    def __init__(self, rooms: Iterable[Room] = ()) -> None:
        self._rooms: dict[str, Room] = {}
        for room in rooms:
            self.add(room)

    def __iter__(self) -> Iterator[Room]:
        """Iterate over the rooms in id order."""
        return iter(sorted(self._rooms.values(), key=lambda room: room.room_id))

    def add(self, room: Room) -> None:
        """Add a room; raises ValueError when its id is already used."""
        if room.room_id in self._rooms:
            raise ValueError(f"duplicate room id {room.room_id!r}")
        self._rooms[room.room_id] = room

    def get(self, room_id: str) -> Room:
        """Return the room with this id, or raise UnknownRoom."""
        try:
            return self._rooms[room_id]
        except KeyError:
            raise UnknownRoom(room_id) from None

    def suitable(self, attendees: int, needs: Iterable[str] = ()) -> list[Room]:
        """Return the rooms that fit a meeting, smallest first and then by id.

        Offering the smallest room first keeps the big rooms free for big meetings.
        """
        wanted = set(needs)
        fitting = [room for room in self._rooms.values() if room.suits(attendees, wanted)]
        return sorted(fitting, key=lambda room: (room.capacity, room.room_id))
