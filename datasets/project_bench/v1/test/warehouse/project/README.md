# warehouse

Back-office code for a small warehouse.

- `stock`: units of each SKU per bin, and reservations for open customer orders.
- `purchasing`: purchase orders, booking supplier deliveries (partial deliveries are
  normal, over-deliveries are refused) and reorder suggestions.
- `picking`: which bins a customer order is picked from, and grouping orders into
  pick waves.
- `shipping`: packing orders into parcels of at most 25 kg and pricing them with the
  carrier, who bills every started kilogram.
- `reports`: stock value, low-stock list and a CSV extract for the office.
- `storage`: a SQLite log of stock movements for audits.

Run the tests with `python -m pytest`.
