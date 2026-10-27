# pharmacy

Counter software for a small community pharmacy.

- `models` holds the records: staff, medicines, batches, picks and prescriptions.
- `inventory` keeps stock per batch. A batch can be sold up to and including its expiry
  date, and stock always leaves first-expiring first (FEFO).
- `prescriptions` files prescriptions, enforces the refill limit (the first fill is not a
  refill) and checks each dose against the medicine's single-dose and daily limits.
- `controlled` records requests and approvals for controlled medicines. Only an active
  pharmacist may approve a fill.
- `receipts` numbers receipts, adds 5% VAT (rounded half up to the cent) and prints them.
- `dispensing` is the counter that ties these together.

Run the tests with `pytest`.
