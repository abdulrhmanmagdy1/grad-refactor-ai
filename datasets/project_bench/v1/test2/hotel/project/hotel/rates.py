"""Seasonal nightly rates and money helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from hotel.rooms import RoomType

CENT = Decimal("0.01")


def to_money(amount: Decimal) -> Decimal:
    """Round an amount to whole cents, halves rounding up."""
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def nights_between(check_in: date, check_out: date) -> list[date]:
    """Return the nights of a stay: every date from check-in up to the day before check-out.

    A stay lasts at least one night, so check-out must come after check-in.
    """
    if check_out <= check_in:
        raise ValueError("check-out must be after check-in")
    return [check_in + timedelta(days=offset) for offset in range((check_out - check_in).days)]


@dataclass(frozen=True)
class Season:
    """A period, both ends included, in which every base rate is multiplied by `multiplier`."""

    name: str
    start: date
    end: date
    multiplier: Decimal

    def contains(self, day: date) -> bool:
        """Whether the night of `day` falls in this season."""
        return self.start <= day <= self.end


class RateTable:
    """Nightly prices per room type, adjusted by season.

    A night outside every season costs the base rate. When seasons overlap, the season
    that was added first wins.
    """

    def __init__(self, seasons: Iterable[Season] = ()) -> None:
        self._seasons: list[Season] = []
        for season in seasons:
            self.add_season(season)

    def add_season(self, season: Season) -> None:
        """Add a season after the existing ones."""
        if season.end < season.start:
            raise ValueError(f"season {season.name} ends before it starts")
        if season.multiplier <= 0:
            raise ValueError("a season multiplier must be positive")
        self._seasons.append(season)

    def season_for(self, day: date) -> Season | None:
        """Return the season the night of `day` falls in, or None."""
        for season in self._seasons:
            if season.contains(day):
                return season
        return None

    def nightly_rate(self, room_type: RoomType, day: date) -> Decimal:
        """Price of one night in a room of this type, starting on `day`."""
        season = self.season_for(day)
        multiplier = season.multiplier if season is not None else Decimal(1)
        return to_money(room_type.base_rate * multiplier)

    def stay_price(self, room_type: RoomType, check_in: date, check_out: date) -> Decimal:
        """Price of a whole stay: each night at the rate of the season it falls in."""
        total = Decimal("0.00")
        for night in nights_between(check_in, check_out):
            total += self.nightly_rate(room_type, night)
        return total
