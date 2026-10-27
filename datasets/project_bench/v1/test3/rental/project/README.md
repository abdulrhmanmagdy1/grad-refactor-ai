# rental

Back office of a small car rental agency with several branches.

- `rates.py` holds the rate card: the daily rate, included kilometres per day,
  excess mileage price and deposit of each vehicle class, plus the prices of extras.
- `fleet.py` knows the branches and the cars parked at each one.
- `contracts.py` opens a contract when a customer picks a car up and closes it when the
  car comes back. A car may be dropped off at another branch (a one-way rental, with a
  flat fee); it then stays at the drop-off branch.
- `invoice.py` bills a returned contract: booked days, extras per booked day, one-way
  fee, excess mileage, late days and damage, plus 14% sales tax. The deposit held at
  pick-up is set against the total.
- `report.py` prints what each branch needs in the morning.

Billing rules:

- Days are counted in started 24-hour periods with a minimum of one day.
- A car returned up to 59 minutes after it was due is on time. Later than that, every
  started day after the due time is a late day at 1.5 times the daily rate.
- Drivers must be at least 21; drivers under 25 pay the young-driver extra.
- Only a manager of the drop-off branch may waive a damage charge.
