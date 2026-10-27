# project-bench-v2 results

- test / static: started 2026-10-24T18:12:13+00:00, commit a072b9faad, frozen
- test / full-14b: started 2026-10-27T08:25:00+00:00, commit , not frozen

| | static | full-14b |
|---|---|---|
| Projects | 8 | 8 |
| Seeded issues located (a finding on the place) | 18/55 (33%, 22% to 46%) | 36/55 (65%, 52% to 77%) |
| ... architecture | 4/8 (50%, 22% to 78%) | 7/8 (88%, 53% to 98%) |
| ... bug | 4/24 (17%, 7% to 36%) | 12/24 (50%, 31% to 69%) |
| ... quality | 6/15 (40%, 20% to 64%) | 10/15 (67%, 42% to 85%) |
| ... security | 4/8 (50%, 22% to 78%) | 7/8 (88%, 53% to 98%) |
| Seeded issues found (judge confirmed) | 18/55 (33%, 22% to 46%) | 27/55 (49%, 36% to 62%) |
| ... architecture | 4/8 (50%, 22% to 78%) | 4/8 (50%, 22% to 78%) |
| ... bug | 4/24 (17%, 7% to 36%) | 10/24 (42%, 24% to 61%) |
| ... quality | 6/15 (40%, 20% to 64%) | 7/15 (47%, 25% to 70%) |
| ... security | 4/8 (50%, 22% to 78%) | 6/8 (75%, 41% to 93%) |
| Located issues not judged yet | 0 | 0 |
| Findings | 27 | 164 |
| ... on a seeded issue | 21/27 (78%, 59% to 89%) | 69/164 (42%, 35% to 50%) |
| ... on a decoy | 6 | 11 |
| ... elsewhere (unlabelled) | 0 | 84 |
| Decoys flagged | 6/16 (38%, 18% to 61%) | 9/16 (56%, 33% to 77%) |
| Fixable issues fixed by the ready fixes | 0/32 (0%, 0% to 11%) | 1/32 (3%, 1% to 16%) |
| Fixable issues fixed by some fix | 0/32 (0%, 0% to 11%) | 14/32 (44%, 28% to 61%) |
| Ready fixes | 0 | 1 |
| Ready fixes that break a test | 0 | 0 |
| Median review time (s) | 1.55 | 611.83 |
| Model calls | 0 | 624 |

Paired detection, located (first arm vs second arm, same issues): both 18, only first 0, only second 18, neither 19, exact McNemar p = 8e-06.

Paired detection, judge confirmed (first arm vs second arm, same issues): both 18, only first 0, only second 9, neither 28, exact McNemar p = 0.003906.

## Per project

| Arm | Project | Found | Missed | Decoys | Fixed |
|---|---|---|---|---|---|
| static | clinic | S1 Q1 | B1 B2 B3 A1 Q2 | D1 | - |
| static | gradebook | B1 A1 | B2 B3 S1 Q1 Q2 | - | - |
| static | ledger | S1 Q2 | B1 B2 B3 A1 Q1 | D1 D2 | - |
| static | pipeline | B1 A1 | B2 B3 S1 Q1 Q2 | D1 | - |
| static | scheduler | B2 A1 Q1 | B1 B3 S1 Q2 | - | - |
| static | textstats | B1 A1 Q1 | B2 B3 S1 Q2 | D1 | - |
| static | warehouse | S1 Q1 | B1 B2 B3 A1 | D1 | - |
| static | webapp | S1 Q1 | B1 B2 B3 A1 Q2 | - | - |
| full-14b | clinic | B1 B2 S1 A1 Q1 | B3 Q2 | D1 | - |
| full-14b | gradebook | B1 B2 B3 S1 A1 Q2 | Q1 | D1 D2 | - |
| full-14b | ledger | B3 S1 A1 Q2 | B1 B2 Q1 | D1 D2 | - |
| full-14b | pipeline | B1 B2 A1 Q1 | B3 S1 Q2 | D1 | - |
| full-14b | scheduler | B2 B3 S1 A1 Q1 Q2 | B1 | D1 | - |
| full-14b | textstats | B1 S1 A1 Q1 | B2 B3 Q2 | D1 | B1 |
| full-14b | warehouse | S1 Q1 | B1 B2 B3 A1 | D1 | - |
| full-14b | webapp | B3 S1 A1 Q1 Q2 | B1 B2 | - | - |

## Fixes (disposition / outcome when applied alone)

- static: none
- full-14b: failed/no_proposal: 2, proposal_ready/resolves: 1, rejected/harmful: 26, rejected/no_effect: 13, rejected/no_proposal: 5, rejected/resolves: 1, uncertain/harmful: 1, uncertain/no_effect: 26, uncertain/resolves: 11
