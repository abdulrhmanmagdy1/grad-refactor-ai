# project-bench-v1 results

- test / static: started 2026-10-24T18:12:13+00:00, commit a072b9faad, frozen
- test / full: started 2026-10-24T18:12:45+00:00, commit a072b9faad (dirty), frozen

| | static | full |
|---|---|---|
| Projects | 8 | 8 |
| Seeded issues located (a finding on the place) | 18/55 (33%, 22% to 46%) | 33/55 (60%, 47% to 72%) |
| ... architecture | 4/8 (50%, 22% to 78%) | 8/8 (100%, 68% to 100%) |
| ... bug | 4/24 (17%, 7% to 36%) | 10/24 (42%, 24% to 61%) |
| ... quality | 6/15 (40%, 20% to 64%) | 11/15 (73%, 48% to 89%) |
| ... security | 4/8 (50%, 22% to 78%) | 4/8 (50%, 22% to 78%) |
| Seeded issues found (judge confirmed) | 18/55 (33%, 22% to 46%) | 19/55 (35%, 23% to 48%) |
| ... architecture | 4/8 (50%, 22% to 78%) | 4/8 (50%, 22% to 78%) |
| ... bug | 4/24 (17%, 7% to 36%) | 4/24 (17%, 7% to 36%) |
| ... quality | 6/15 (40%, 20% to 64%) | 7/15 (47%, 25% to 70%) |
| ... security | 4/8 (50%, 22% to 78%) | 4/8 (50%, 22% to 78%) |
| Located issues not judged yet | 0 | 0 |
| Findings | 27 | 155 |
| ... on a seeded issue | 21/27 (78%, 59% to 89%) | 59/155 (38%, 31% to 46%) |
| ... on a decoy | 6 | 11 |
| ... elsewhere (unlabelled) | 0 | 85 |
| Decoys flagged | 6/16 (38%, 18% to 61%) | 8/16 (50%, 28% to 72%) |
| Fixable issues fixed by the ready fixes | 0/32 (0%, 0% to 11%) | 1/32 (3%, 1% to 16%) |
| Fixable issues fixed by some fix | 0/32 (0%, 0% to 11%) | 4/32 (12%, 5% to 28%) |
| Ready fixes | 0 | 1 |
| Ready fixes that break a test | 0 | 0 |
| Median review time (s) | 1.55 | 347.22 |
| Model calls | 0 | 572 |

Paired detection, located (first arm vs second arm, same issues): both 18, only first 0, only second 15, neither 22, exact McNemar p = 6.1e-05.

Paired detection, judge confirmed (first arm vs second arm, same issues): both 18, only first 0, only second 1, neither 36, exact McNemar p = 1.0.

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

## Fixes (disposition / outcome when applied alone)

- static: none
- full: failed/no_proposal: 3, proposal_ready/resolves: 1, rejected/harmful: 12, rejected/no_effect: 20, rejected/no_proposal: 15, uncertain/harmful: 3, uncertain/no_effect: 18, uncertain/resolves: 3
