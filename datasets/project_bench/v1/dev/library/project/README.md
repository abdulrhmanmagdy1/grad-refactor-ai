# library

A lending desk for a small library. Members borrow copies for 14 days and may hold at
most `max_loans` books at a time; returning a book frees the slot. A loan is overdue from
the day after its due date, and the fine is 0.25 per day after the due date, capped at
10.00. Catalog exports are JSON files kept inside one export folder.
