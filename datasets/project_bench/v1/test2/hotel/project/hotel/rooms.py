"""Rooms and room types of the hotel."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal


@dataclass(frozen=True)
class RoomType:
    """A kind of room: its base nightly rate and how many guests it sleeps."""

    code: str
    name: str
    base_rate: Decimal
    capacity: int


@dataclass(frozen=True)
class Room:
    """A physical room. Rooms that are out of service cannot be booked."""

    number: str
    room_type: RoomType
    floor: int
    in_service: bool = True


class RoomCatalog:
    """Every room of the hotel, looked up by room number or by room type."""

    def __init__(self) -> None:
        self._types: dict[str, RoomType] = {}
        self._rooms: dict[str, Room] = {}

    def add_type(self, room_type: RoomType) -> None:
        """Register a room type. Codes are unique and a type sleeps at least one guest."""
        if room_type.code in self._types:
            raise ValueError(f"room type {room_type.code} already exists")
        if room_type.capacity < 1:
            raise ValueError("a room type must sleep at least one guest")
        if room_type.base_rate <= 0:
            raise ValueError("the base rate must be positive")
        self._types[room_type.code] = room_type

    def add_room(self, room: Room) -> None:
        """Register a room whose type is already known. Room numbers are unique."""
        if room.number in self._rooms:
            raise ValueError(f"room {room.number} already exists")
        if room.room_type.code not in self._types:
            raise ValueError(f"unknown room type {room.room_type.code}")
        self._rooms[room.number] = room

    def room(self, number: str) -> Room:
        """Return the room with this number, or raise KeyError."""
        try:
            return self._rooms[number]
        except KeyError:
            raise KeyError(f"no room {number}") from None

    def room_type(self, code: str) -> RoomType:
        """Return the room type with this code, or raise KeyError."""
        try:
            return self._types[code]
        except KeyError:
            raise KeyError(f"no room type {code}") from None

    def all_rooms(self) -> list[Room]:
        """Return every room, in service or not, ordered by room number."""
        return [self._rooms[number] for number in sorted(self._rooms)]

    def rooms_of_type(self, code: str) -> list[Room]:
        """Return the in-service rooms of one type, ordered by room number."""
        self.room_type(code)
        return [
            room
            for room in self.all_rooms()
            if room.room_type.code == code and room.in_service
        ]

    def set_in_service(self, number: str, in_service: bool) -> Room:
        """Take a room out of service or put it back, and return the updated room."""
        updated = replace(self.room(number), in_service=in_service)
        self._rooms[number] = updated
        return updated
