# project-bench-v3 results (test3 split)

Protocol: [docs/evaluation/project-benchmark.md](../../../../docs/evaluation/project-benchmark.md)
(section project-bench-v3). Freeze: [freeze-test3.json](../freeze-test3.json), committed in
55a458a before any review of test3. Final configuration: prompt version project-v5 (mypy,
spec tests with related signatures and one repair round) on Qwen2.5-Coder-14B-Instruct
Q4_K_M, run on Kaggle (2 x T4); the run passed the whole freeze check
(`freeze_problems: []`) and all 784 model calls succeeded. Pairs and the blind judge's
labels (a new session) in [judge/](judge/); full tables in [report.md](report.md).

## Results (8 new projects, 53 seeded issues)

| | Static | Full (project-v5, 14B) |
|---|---|---|
| Issues found, judge confirmed | 18/53 (34%, CI 23% to 47%) | 31/53 (58%, CI 45% to 71%) |
| ... bug | 5/24 | 15/24 |
| ... security | 3/8 | 6/8 |
| ... architecture | 4/8 | 4/8 |
| ... quality | 6/13 | 6/13 |
| Findings (off every seeded place, on decoys) | 25 (0, 1) | 174 (95, 10) |
| Fixable issues fixed by some fix | 0/32 | 16/32 |
| Fixes marked ready (fixing their bug) | 0 | 4 (3) |
| Ready fixes that break a test | 0 | 0 |

Paired, judge confirmed: the full arm found 13 issues static missed and missed none it
found (exact McNemar p = 0.00024).

The spec tests now take part: 171 tests written, 31 repaired after calling the code
wrongly, 12 still set aside as misuse, and 21 failing tests blamed on the code (on test2:
2). One ready fix changes nothing the hidden tests check (no effect), none breaks a test.
