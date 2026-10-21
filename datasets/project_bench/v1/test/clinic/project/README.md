# clinic

Back-office code for a small outpatient clinic.

- `storage.PatientStore` keeps patient records in SQLite and lets the reception search
  them by name.
- `availability` knows each doctor's weekly working hours and lists free slots.
- `scheduling.Schedule` books, cancels and closes appointments. Cancelling with less than
  24 hours' notice costs a fixed late-cancellation fee.
- `insurance` decides whether a policy applies on a given day and splits a bill between
  the patient and the insurer, respecting the policy's annual limit.
- `billing` builds invoices for completed visits and late cancellations and prints them.

Money is handled with `Decimal` and rounded to the cent. Times are naive local times.

Run the tests with `python -m pytest`.
