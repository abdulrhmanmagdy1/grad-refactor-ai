# ledger

Back-office ledger for a small credit union: member accounts, deposits, withdrawals,
transfers, month-end interest and fees, and monthly statements.

- Amounts are `Decimal`, rounded half up to the cent (`ledger.money.to_money`).
- Checking accounts may have an overdraft limit: the balance may go below zero down to
  minus that limit. Savings accounts cannot go below zero.
- Money only moves into and out of open accounts.
- Savings earn tiered interest, paid monthly on the closing balance.
- Checking accounts pay a 5.00 maintenance fee unless their lowest balance of the month
  stayed at 1,000.00 or more. Savings accounts get six free withdrawals a month; each
  further one costs 2.00.
- Data lives in SQLite (`ledger.store.LedgerStore`, in memory by default).

Run the tests with `pytest`.
