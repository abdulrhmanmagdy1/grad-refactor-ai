# project-bench-v2 results

- test2 / static: started 2026-10-27T11:42:06+00:00, commit , not frozen
- test2 / full-14b: started 2026-10-27T11:42:28+00:00, commit , not frozen

| | static | full-14b |
|---|---|---|
| Projects | 8 | 8 |
| Seeded issues located (a finding on the place) | 20/55 (36%, 25% to 50%) | 39/55 (71%, 58% to 81%) |
| ... architecture | 4/8 (50%, 22% to 78%) | 8/8 (100%, 68% to 100%) |
| ... bug | 5/24 (21%, 9% to 40%) | 15/24 (62%, 43% to 79%) |
| ... quality | 8/15 (53%, 30% to 75%) | 10/15 (67%, 42% to 85%) |
| ... security | 3/8 (38%, 14% to 69%) | 6/8 (75%, 41% to 93%) |
| Seeded issues found (judge confirmed) | 19/55 (35%, 23% to 48%) | 28/55 (51%, 38% to 64%) |
| ... architecture | 4/8 (50%, 22% to 78%) | 4/8 (50%, 22% to 78%) |
| ... bug | 5/24 (21%, 9% to 40%) | 13/24 (54%, 35% to 72%) |
| ... quality | 7/15 (47%, 25% to 70%) | 7/15 (47%, 25% to 70%) |
| ... security | 3/8 (38%, 14% to 69%) | 4/8 (50%, 22% to 78%) |
| Located issues not judged yet | 0 | 0 |
| Findings | 28 | 166 |
| ... on a seeded issue | 26/28 (93%, 77% to 98%) | 72/166 (43%, 36% to 51%) |
| ... on a decoy | 2 | 9 |
| ... elsewhere (unlabelled) | 0 | 85 |
| Decoys flagged | 2/16 (12%, 4% to 36%) | 6/16 (38%, 18% to 61%) |
| Fixable issues fixed by the ready fixes | 0/32 (0%, 0% to 11%) | 1/32 (3%, 1% to 16%) |
| Fixable issues fixed by some fix | 0/32 (0%, 0% to 11%) | 14/32 (44%, 28% to 61%) |
| Ready fixes | 0 | 1 |
| Ready fixes that break a test | 0 | 0 |
| Median review time (s) | 0.98 | 852.06 |
| Model calls | 0 | 693 |

Paired detection, located (first arm vs second arm, same issues): both 20, only first 0, only second 19, neither 16, exact McNemar p = 4e-06.

Paired detection, judge confirmed (first arm vs second arm, same issues): both 19, only first 0, only second 9, neither 27, exact McNemar p = 0.003906.

## Per project

| Arm | Project | Found | Missed | Decoys | Fixed |
|---|---|---|---|---|---|
| static | budget | S1 | B1 B2 B3 A1 Q1 Q2 | D1 | - |
| static | enrollment | B1 Q1 | B2 B3 S1 A1 Q2 | - | - |
| static | fleet | B2 Q1 | B1 B3 S1 A1 | - | - |
| static | forum | B1 A1 Q1 Q2 | B2 B3 S1 | - | - |
| static | hotel | B2 A1 Q1 | B1 B3 S1 Q2 | - | - |
| static | payroll | S1 Q1 | B1 B2 B3 A1 Q2 | D1 | - |
| static | ticketing | S1 A1 Q2 | B1 B2 B3 Q1 | - | - |
| static | weatherlog | B3 A1 Q1 | B1 B2 S1 Q2 | - | - |
| full-14b | budget | B1 B2 S1 A1 Q1 | B3 Q2 | D1 D2 | - |
| full-14b | enrollment | B1 B2 B3 S1 A1 Q1 | Q2 | - | - |
| full-14b | fleet | B1 B2 B3 A1 Q1 | S1 | D2 | - |
| full-14b | forum | B1 B2 A1 Q1 Q2 | B3 S1 | D2 | - |
| full-14b | hotel | B2 B3 S1 A1 Q1 | B1 Q2 | D1 | B2 |
| full-14b | payroll | S1 A1 Q1 | B1 B2 B3 Q2 | D1 | - |
| full-14b | ticketing | B3 S1 A1 Q2 | B1 B2 Q1 | - | - |
| full-14b | weatherlog | B2 B3 S1 A1 Q1 Q2 | B1 | - | - |

## Fixes (disposition / outcome when applied alone)

- static: none
- full-14b: proposal_ready/resolves: 1, rejected/harmful: 23, rejected/no_effect: 12, rejected/no_proposal: 7, rejected/resolves: 1, uncertain/harmful: 2, uncertain/no_effect: 21, uncertain/resolves: 9
