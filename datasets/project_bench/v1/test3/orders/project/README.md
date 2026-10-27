# orders

Backend of a small online shop. All money is `Decimal`, rounded to cents half up.

- `catalog.py`: products, variants (colour, size) and the stock of each variant. Stock is
  taken when an order is placed and put back when an order is cancelled or returned.
- `cart.py`: shopping carts, one line per variant.
- `coupons.py`: percentage or fixed coupon codes with an expiry day, a minimum subtotal and
  single-use codes.
- `shipping.py`: shipping cost from the destination zone and the parcel weight. The carrier
  bills every started kilogram; orders from 75.00 ship free.
- `order.py`: orders and their states. An order is placed, then paid, then shipped; a
  customer can cancel their own order before it ships or return their own shipped order.
  Cancelled and returned orders can be refunded in one or more parts, never more than was
  paid in total.
- `checkout.py`: pricing a cart and turning it into an order.
- `store.py`: saving orders to SQLite and exporting them to CSV.
- `utils.py`: shared helpers.

Run the tests with `pytest`.
