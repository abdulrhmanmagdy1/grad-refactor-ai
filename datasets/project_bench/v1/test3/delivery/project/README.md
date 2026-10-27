# delivery

A small food delivery service.

- Restaurants have weekly opening windows. A window may run past midnight
  (18:00 to 02:00 covers the early hours of the next day). Opening time is
  inclusive, closing time exclusive.
- Order lines name menu items and their options; the food subtotal is the sum
  of (item price + option prices) x quantity. Money is `Decimal`.
- The delivery fee depends on the distance from the restaurant to the
  customer, rounded to 0.1 km: up to and including 2 km costs 1.50, up to and
  including 5 km costs 2.90, up to and including 8 km costs 4.50. Farther
  away is outside the delivery area. Orders under 12.00 pay a 1.00 surcharge.
- Tips are a percentage of the food subtotal, rounded half up to the cent.
- The free courier closest to the restaurant picks the order up.
- The delivery estimate is the longer of preparation and the courier's ride
  to the restaurant, plus the ride to the customer and 3 minutes handover.
- Each order gets a secret tracking token for the customer.
