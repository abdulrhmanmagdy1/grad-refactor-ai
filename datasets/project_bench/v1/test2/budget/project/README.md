# budget

A small personal finance tool. `budget.ledger` keeps accounts and their
transactions in SQLite (money is stored as Decimal text, never float).
`budget.recurring` posts monthly transactions such as rent or salary,
`budget.budgets` tracks monthly budgets per category, optionally rolling unspent
money over into the next month, and `budget.summary` and `budget.report` produce
spending summaries.
