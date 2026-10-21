# parking

The software of a small multi-level car park.

Each level has standard, compact, EV and accessible spaces, and a car is given the free
space of its kind on the lowest level. Drivers pay for every started hour, but each 24
hours of a stay cost at most the daily cap; the first 15 minutes are free. A driver who
lost the ticket pays the stay plus a fixed fee. Cars with a valid monthly permit park free;
a permit bought on 15 March for one month works up to and including 14 April.

Closed tickets are kept in an SQLite log. The monthly revenue report lists parking revenue
per day (on the day the car left) and per level, permit sales, and the total with the VAT it
includes (all prices include 20% VAT).
