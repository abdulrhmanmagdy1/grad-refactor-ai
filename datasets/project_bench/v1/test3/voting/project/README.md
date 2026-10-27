# voting

Election software for a members' club.

- `voters` keeps the membership roll. A member may vote when their dues are paid, they
  are not suspended and they joined at least 90 days before election day.
- `ballots` issues each eligible member one voting token and takes ranked ballots. A
  ranking names at least one candidate, only candidates who are standing, and each
  candidate at most once. Ballots are stored without the member's id.
- `counting` counts the ballots by instant runoff: each round is counted from the
  ballots, a candidate with more than half of the counted ballots wins, otherwise the
  candidate with the fewest votes is eliminated.
- `quorum` decides whether enough members voted: a third of the eligible members,
  rounded up.
- `audit` keeps a hash-chained log of every step and can point out suspicious activity.
- `export` writes the result as JSON and CSV into a results folder.
- `election` closes an election: quorum check, count, audit entry and export.

Run the tests with `pytest`.
