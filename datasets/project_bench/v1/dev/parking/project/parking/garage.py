"""The levels and spaces of the garage, and which car is parked where."""

from __future__ import annotations

from parking.models import Space

KINDS = ("standard", "compact", "ev", "accessible")


class Garage:
    """Every space of every level, by space code."""

    def __init__(self) -> None:
        self.spaces: dict[str, Space] = {}

    @property
    def levels(self) -> list[int]:
        return sorted({space.level for space in self.spaces.values()})

    def add_level(self, level: int, layout: dict[str, int]) -> None:
        """Add a level with `layout[kind]` spaces of each kind, numbered from 1."""
        if level in self.levels:
            raise ValueError(f"level {level} already exists")
        unknown = set(layout) - set(KINDS)
        if unknown:
            raise ValueError(f"unknown space kinds: {sorted(unknown)}")
        number = 1
        for kind, count in layout.items():
            for _ in range(count):
                space = Space(level, number, kind)
                self.spaces[space.code] = space
                number += 1

    def find_space(self, kind: str = "standard") -> Space | None:
        """The free space of this kind on the lowest level, lowest number first."""
        free = [space for space in self.spaces.values() if space.kind == kind and space.is_free]
        return min(free, key=lambda space: (space.level, space.number), default=None)

    def where_is(self, plate: str) -> Space | None:
        """The space a car is parked in, if it is in the garage."""
        return next((space for space in self.spaces.values() if space.plate == plate), None)

    def park(self, plate: str, kind: str = "standard") -> Space:
        """Put a car in the best free space of its kind."""
        if self.where_is(plate) is not None:
            raise ValueError(f"{plate} is already parked")
        space = self.find_space(kind)
        if space is None:
            raise LookupError(f"no free {kind} space")
        space.plate = plate
        return space

    def leave(self, code: str) -> str:
        """Free a space and return the plate of the car that was parked there."""
        space = self.spaces[code]
        if space.plate is None:
            raise ValueError(f"space {code} is already free")
        plate = space.plate
        space.plate = None
        return plate

    def occupancy(self) -> dict[int, float]:
        """The share of occupied spaces on each level, from 0.0 to 1.0."""
        result: dict[int, float] = {}
        for level in self.levels:
            spaces = [space for space in self.spaces.values() if space.level == level]
            taken = sum(1 for space in spaces if not space.is_free)
            result[level] = taken / len(spaces)
        return result
