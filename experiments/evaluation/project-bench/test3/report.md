# project-bench-v3 results

- test3 / static: started 2026-10-27T19:22:33+00:00, commit , not frozen
- test3 / full-14b: started 2026-10-27T19:23:07+00:00, commit , not frozen

| | static | full-14b |
|---|---|---|
| Projects | 8 | 8 |
| Seeded issues located (a finding on the place) | 18/53 (34%, 23% to 47%) | 37/53 (70%, 56% to 80%) |
| ... architecture | 4/8 (50%, 22% to 78%) | 5/8 (62%, 31% to 86%) |
| ... bug | 5/24 (21%, 9% to 40%) | 17/24 (71%, 51% to 85%) |
| ... quality | 6/13 (46%, 23% to 71%) | 9/13 (69%, 42% to 87%) |
| ... security | 3/8 (38%, 14% to 69%) | 6/8 (75%, 41% to 93%) |
| Seeded issues found (judge confirmed) | 18/53 (34%, 23% to 47%) | 31/53 (58%, 45% to 71%) |
| ... architecture | 4/8 (50%, 22% to 78%) | 4/8 (50%, 22% to 78%) |
| ... bug | 5/24 (21%, 9% to 40%) | 15/24 (62%, 43% to 79%) |
| ... quality | 6/13 (46%, 23% to 71%) | 6/13 (46%, 23% to 71%) |
| ... security | 3/8 (38%, 14% to 69%) | 6/8 (75%, 41% to 93%) |
| Located issues not judged yet | 0 | 0 |
| Findings | 25 | 174 |
| ... on a seeded issue | 24/25 (96%, 80% to 99%) | 69/174 (40%, 33% to 47%) |
| ... on a decoy | 1 | 10 |
| ... elsewhere (unlabelled) | 0 | 95 |
| Decoys flagged | 1/16 (6%, 1% to 28%) | 8/16 (50%, 28% to 72%) |
| Fixable issues fixed by the ready fixes | 0/32 (0%, 0% to 11%) | 3/32 (9%, 3% to 24%) |
| Fixable issues fixed by some fix | 0/32 (0%, 0% to 11%) | 16/32 (50%, 34% to 66%) |
| Ready fixes | 0 | 4 |
| Ready fixes that break a test | 0 | 0 |
| Median review time (s) | 2.29 | 1046.53 |
| Model calls | 0 | 784 |

Paired detection, located (first arm vs second arm, same issues): both 18, only first 0, only second 19, neither 16, exact McNemar p = 4e-06.

Paired detection, judge confirmed (first arm vs second arm, same issues): both 18, only first 0, only second 13, neither 22, exact McNemar p = 0.000244.

## Per project

| Arm | Project | Found | Missed | Decoys | Fixed |
|---|---|---|---|---|---|
| static | crm | B1 Q1 | B2 B3 S1 A1 Q2 | - | - |
| static | delivery | S1 A1 Q1 | B1 B2 B3 | - | - |
| static | gym | S1 A1 Q2 | B1 B2 B3 Q1 | - | - |
| static | helpdesk | B1 Q1 | B2 B3 S1 A1 | - | - |
| static | orders | B1 Q1 | B2 B3 S1 A1 Q2 | D1 | - |
| static | pharmacy | B1 A1 | B2 B3 S1 Q1 Q2 | - | - |
| static | rental | B3 A1 | B1 B2 S1 Q1 Q2 | - | - |
| static | voting | S1 Q1 | B1 B2 B3 A1 | - | - |
| full-14b | crm | B1 S1 Q1 | B2 B3 A1 Q2 | - | - |
| full-14b | delivery | B1 B2 B3 S1 A1 Q1 | - | D1 D2 | B1 |
| full-14b | gym | B2 B3 S1 A1 Q1 Q2 | B1 | - | - |
| full-14b | helpdesk | B1 B2 S1 Q1 | B3 A1 | D2 | - |
| full-14b | orders | B1 B3 Q1 Q2 | B2 S1 A1 | D1 | - |
| full-14b | pharmacy | B1 B2 B3 S1 A1 Q1 | Q2 | D1 D2 | B1 |
| full-14b | rental | B3 A1 | B1 B2 S1 Q1 Q2 | D1 | B3 |
| full-14b | voting | B1 B2 B3 S1 A1 Q1 | - | D2 | - |

## Fixes (disposition / outcome when applied alone)

- static: none
- full-14b: proposal_ready/no_effect: 1, proposal_ready/resolves: 3, rejected/harmful: 32, rejected/no_effect: 15, rejected/no_proposal: 8, rejected/resolves: 2, uncertain/harmful: 1, uncertain/no_effect: 12, uncertain/resolves: 10
