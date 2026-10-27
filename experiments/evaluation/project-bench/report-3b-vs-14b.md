# project-bench-v2 results

- test / full: started 2026-10-24T18:12:45+00:00, commit a072b9faad (dirty), frozen
- test / full-14b: started 2026-10-27T08:25:00+00:00, commit , not frozen

| | full | full-14b |
|---|---|---|
| Projects | 8 | 8 |
| Seeded issues located (a finding on the place) | 33/55 (60%, 47% to 72%) | 36/55 (65%, 52% to 77%) |
| ... architecture | 8/8 (100%, 68% to 100%) | 7/8 (88%, 53% to 98%) |
| ... bug | 10/24 (42%, 24% to 61%) | 12/24 (50%, 31% to 69%) |
| ... quality | 11/15 (73%, 48% to 89%) | 10/15 (67%, 42% to 85%) |
| ... security | 4/8 (50%, 22% to 78%) | 7/8 (88%, 53% to 98%) |
| Seeded issues found (judge confirmed) | 19/55 (35%, 23% to 48%) | 27/55 (49%, 36% to 62%) |
| ... architecture | 4/8 (50%, 22% to 78%) | 4/8 (50%, 22% to 78%) |
| ... bug | 4/24 (17%, 7% to 36%) | 10/24 (42%, 24% to 61%) |
| ... quality | 7/15 (47%, 25% to 70%) | 7/15 (47%, 25% to 70%) |
| ... security | 4/8 (50%, 22% to 78%) | 6/8 (75%, 41% to 93%) |
| Located issues not judged yet | 0 | 0 |
| Findings | 155 | 164 |
| ... on a seeded issue | 59/155 (38%, 31% to 46%) | 69/164 (42%, 35% to 50%) |
| ... on a decoy | 11 | 11 |
| ... elsewhere (unlabelled) | 85 | 84 |
| Decoys flagged | 8/16 (50%, 28% to 72%) | 9/16 (56%, 33% to 77%) |
| Fixable issues fixed by the ready fixes | 1/32 (3%, 1% to 16%) | 1/32 (3%, 1% to 16%) |
| Fixable issues fixed by some fix | 4/32 (12%, 5% to 28%) | 14/32 (44%, 28% to 61%) |
| Ready fixes | 1 | 1 |
| Ready fixes that break a test | 0 | 0 |
| Median review time (s) | 347.22 | 611.83 |
| Model calls | 572 | 624 |

Paired detection, located (first arm vs second arm, same issues): both 30, only first 3, only second 6, neither 16, exact McNemar p = 0.507812.

Paired detection, judge confirmed (first arm vs second arm, same issues): both 19, only first 0, only second 8, neither 28, exact McNemar p = 0.007812.

## Per project

| Arm | Project | Found | Missed | Decoys | Fixed |
|---|---|---|---|---|---|
| full | clinic | B1 S1 A1 Q1 | B2 B3 Q2 | D1 | - |
| full | gradebook | B1 A1 Q1 Q2 | B2 B3 S1 | - | - |
| full | ledger | B3 S1 A1 Q2 | B1 B2 Q1 | D1 D2 | - |
| full | pipeline | B1 B2 A1 Q1 | B3 S1 Q2 | D1 | - |
| full | scheduler | B2 B3 A1 Q1 Q2 | B1 S1 | D1 | - |
| full | textstats | B1 A1 Q1 | B2 B3 S1 Q2 | D1 | B1 |
| full | warehouse | S1 A1 Q1 | B1 B2 B3 | D1 D2 | - |
| full | webapp | B1 B3 S1 A1 Q1 Q2 | B2 | - | - |
| full-14b | clinic | B1 B2 S1 A1 Q1 | B3 Q2 | D1 | - |
| full-14b | gradebook | B1 B2 B3 S1 A1 Q2 | Q1 | D1 D2 | - |
| full-14b | ledger | B3 S1 A1 Q2 | B1 B2 Q1 | D1 D2 | - |
| full-14b | pipeline | B1 B2 A1 Q1 | B3 S1 Q2 | D1 | - |
| full-14b | scheduler | B2 B3 S1 A1 Q1 Q2 | B1 | D1 | - |
| full-14b | textstats | B1 S1 A1 Q1 | B2 B3 Q2 | D1 | B1 |
| full-14b | warehouse | S1 Q1 | B1 B2 B3 A1 | D1 | - |
| full-14b | webapp | B3 S1 A1 Q1 Q2 | B1 B2 | - | - |

## Fixes (disposition / outcome when applied alone)

- full: failed/no_proposal: 3, proposal_ready/resolves: 1, rejected/harmful: 12, rejected/no_effect: 20, rejected/no_proposal: 15, uncertain/harmful: 3, uncertain/no_effect: 18, uncertain/resolves: 3
- full-14b: failed/no_proposal: 2, proposal_ready/resolves: 1, rejected/harmful: 26, rejected/no_effect: 13, rejected/no_proposal: 5, rejected/resolves: 1, uncertain/harmful: 1, uncertain/no_effect: 26, uncertain/resolves: 11
