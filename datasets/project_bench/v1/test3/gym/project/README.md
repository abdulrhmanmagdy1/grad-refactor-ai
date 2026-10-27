# gym

Back office for a single gym.

- `models.py`: plans, members and memberships. A membership is valid from its start date
  through its expiry date, both included, except on frozen days.
- `memberships.py`: registering members, selling, freezing and cancelling
  memberships. A freeze covers its first and last day, pushes the expiry date back by the
  same number of days and costs a fixed fee.
- `classes.py`: the class timetable. Full classes have a waitlist that is served first come,
  first served.
- `checkins.py`: entry tokens for the members' app and the visit log. One check-in per member
  per day.
- `trainers.py`: one-to-one personal training sessions; late cancellations are charged.
- `billing.py`: the monthly ledger. Charges collect during the month and `close_month` turns
  them into invoices.
- `reports.py`: the month-end summary for the manager.

Money is `Decimal`, rounded to cents half up. Run the tests with `pytest`.
