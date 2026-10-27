# project-bench-v2 results

- test / static: started 2026-10-24T18:12:13+00:00, commit a072b9faad, frozen
- test / full: started 2026-10-24T18:12:45+00:00, commit a072b9faad (dirty), frozen
- test / full-14b: started 2026-10-27T08:25:00+00:00, commit , not frozen
- test / full-32b: started 2026-10-27T08:32:12+00:00, commit , not frozen

| | static | full | full-14b | full-32b |
|---|---|---|---|---|
| Projects | 8 | 8 | 8 | 8 |
| Seeded issues located (a finding on the place) | 18/55 (33%, 22% to 46%) | 33/55 (60%, 47% to 72%) | 36/55 (65%, 52% to 77%) | 32/55 (58%, 45% to 70%) |
| ... architecture | 4/8 (50%, 22% to 78%) | 8/8 (100%, 68% to 100%) | 7/8 (88%, 53% to 98%) | 7/8 (88%, 53% to 98%) |
| ... bug | 4/24 (17%, 7% to 36%) | 10/24 (42%, 24% to 61%) | 12/24 (50%, 31% to 69%) | 11/24 (46%, 28% to 65%) |
| ... quality | 6/15 (40%, 20% to 64%) | 11/15 (73%, 48% to 89%) | 10/15 (67%, 42% to 85%) | 10/15 (67%, 42% to 85%) |
| ... security | 4/8 (50%, 22% to 78%) | 4/8 (50%, 22% to 78%) | 7/8 (88%, 53% to 98%) | 4/8 (50%, 22% to 78%) |
| Seeded issues found (judge confirmed) | 18/55 (33%, 22% to 46%) | 19/55 (35%, 23% to 48%) | 27/55 (49%, 36% to 62%) | 27/55 (49%, 36% to 62%) |
| ... architecture | 4/8 (50%, 22% to 78%) | 4/8 (50%, 22% to 78%) | 4/8 (50%, 22% to 78%) | 4/8 (50%, 22% to 78%) |
| ... bug | 4/24 (17%, 7% to 36%) | 4/24 (17%, 7% to 36%) | 10/24 (42%, 24% to 61%) | 10/24 (42%, 24% to 61%) |
| ... quality | 6/15 (40%, 20% to 64%) | 7/15 (47%, 25% to 70%) | 7/15 (47%, 25% to 70%) | 9/15 (60%, 36% to 80%) |
| ... security | 4/8 (50%, 22% to 78%) | 4/8 (50%, 22% to 78%) | 6/8 (75%, 41% to 93%) | 4/8 (50%, 22% to 78%) |
| Located issues not judged yet | 0 | 0 | 0 | 0 |
| Findings | 27 | 155 | 164 | 103 |
| ... on a seeded issue | 21/27 (78%, 59% to 89%) | 59/155 (38%, 31% to 46%) | 69/164 (42%, 35% to 50%) | 47/103 (46%, 36% to 55%) |
| ... on a decoy | 6 | 11 | 11 | 8 |
| ... elsewhere (unlabelled) | 0 | 85 | 84 | 48 |
| Decoys flagged | 6/16 (38%, 18% to 61%) | 8/16 (50%, 28% to 72%) | 9/16 (56%, 33% to 77%) | 8/16 (50%, 28% to 72%) |
| Fixable issues fixed by the ready fixes | 0/32 (0%, 0% to 11%) | 1/32 (3%, 1% to 16%) | 1/32 (3%, 1% to 16%) | 4/32 (12%, 5% to 28%) |
| Fixable issues fixed by some fix | 0/32 (0%, 0% to 11%) | 4/32 (12%, 5% to 28%) | 14/32 (44%, 28% to 61%) | 13/32 (41%, 26% to 58%) |
| Ready fixes | 0 | 1 | 1 | 4 |
| Ready fixes that break a test | 0 | 0 | 0 | 0 |
| Median review time (s) | 1.55 | 347.22 | 611.83 | 1008.98 |
| Model calls | 0 | 572 | 624 | 498 |

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
| full-32b | clinic | B2 S1 A1 Q1 | B1 B3 Q2 | D1 | - |
| full-32b | gradebook | B1 B2 B3 A1 Q1 | S1 Q2 | - | - |
| full-32b | ledger | B1 B3 S1 A1 Q2 | B2 Q1 | D1 D2 | - |
| full-32b | pipeline | B1 B2 A1 Q2 | B3 S1 Q1 | D1 | B1 |
| full-32b | scheduler | B2 A1 Q1 Q2 | B1 B3 S1 | D1 D2 | B2 |
| full-32b | textstats | B1 A1 Q1 | B2 B3 S1 Q2 | D1 | B1 |
| full-32b | warehouse | B1 S1 A1 Q1 | B2 B3 | D1 | S1 |
| full-32b | webapp | S1 Q1 Q2 | B1 B2 B3 A1 | - | - |

## Fixes (disposition / outcome when applied alone)

- static: none
- full: failed/no_proposal: 3, proposal_ready/resolves: 1, rejected/harmful: 12, rejected/no_effect: 20, rejected/no_proposal: 15, uncertain/harmful: 3, uncertain/no_effect: 18, uncertain/resolves: 3
- full-14b: failed/no_proposal: 2, proposal_ready/resolves: 1, rejected/harmful: 26, rejected/no_effect: 13, rejected/no_proposal: 5, rejected/resolves: 1, uncertain/harmful: 1, uncertain/no_effect: 26, uncertain/resolves: 11
- full-32b: proposal_ready/resolves: 4, rejected/harmful: 9, rejected/no_effect: 2, rejected/no_proposal: 12, uncertain/harmful: 1, uncertain/no_effect: 21, uncertain/resolves: 9
