# hotel

Room inventory and front-office logic for a small hotel.

- `hotel.rooms`: room types (base rate, capacity) and the rooms of the hotel.
- `hotel.rates`: seasonal multipliers on the base rate; a stay is priced night by night.
- `hotel.reservations`: bookings, availability and the reservation book. A stay runs from
  the check-in day to the check-out day; the guest does not sleep there on the check-out
  night, so the room can be sold again from that day.
- `hotel.cancellation`: the cancellation fee policy.
- `hotel.invoice`: invoices (room, extras, 14% VAT) and the invoice archive.
- `hotel.reports`: occupancy, arrivals, departures and revenue.

Money is `decimal.Decimal`, rounded to cents with halves rounding up.

Run the tests with `pytest`.
