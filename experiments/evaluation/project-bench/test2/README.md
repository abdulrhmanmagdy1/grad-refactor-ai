# project-bench-v2 results (test2 split)

Protocol: [docs/evaluation/project-benchmark.md](../../../../docs/evaluation/project-benchmark.md)
(section project-bench-v2). Freeze: [freeze-test2.json](../freeze-test2.json), committed
in 6c70b3e before any review of test2. The full arm ran on Kaggle (2 x T4) with
`bartowski/Qwen2.5-Coder-14B-Instruct-GGUF` Q4_K_M; its run passed the whole freeze check,
model included (`freeze_problems: []`). All 693 model calls succeeded.

| File | What it is |
|---|---|
| [test2-static/](test2-static/) | Static arm |
| [test2-full-14b/](test2-full-14b/) | Full arm, prompt version project-v4 with spec tests, 14B |
| [judge/pairs.jsonl](judge/pairs.jsonl), [judge/labels.json](judge/labels.json) | 73 located pairs and the blind judge's labels (a new judge session) |
| [report.md](report.md), [report.json](report.json) | Full tables |
| [kaggle-status.json](kaggle-status.json) | The Kaggle kernel's steps, hardware and bundle hash |

## Results (8 new projects, 55 seeded issues)

| | Static | Full (project-v4, 14B) |
|---|---|---|
| Issues found, judge confirmed | 19/55 (35%, CI 23% to 48%) | 28/55 (51%, CI 38% to 64%) |
| ... bug | 5/24 | 13/24 |
| ... security | 3/8 | 4/8 |
| ... architecture | 4/8 | 4/8 |
| ... quality | 7/15 | 7/15 |
| Findings (off every seeded place, on decoys) | 28 (0, 2) | 166 (85, 9) |
| Fixable issues fixed by some fix | 0/32 | 14/32 |
| Fixable issues fixed by the ready fixes | 0/32 | 1/32 |
| Ready fixes that break a test | 0 | 0 |
| Median review time | 1.0 s | 852 s (T4) |

Paired, judge confirmed: the full arm found 9 issues static missed and missed none it
found (exact McNemar p = 0.0039).

Of the 76 fixes, 25 break a test when applied: 23 were rejected and 2 stayed uncertain,
none ready. 10 fixes that fix their bug stayed uncertain or were rejected.

The spec tests contributed little: the tester wrote 156 tests, 111 failed on the
project, and the misuse filter (added after the first v4 dev run) set 102 of those aside
because they failed with a TypeError, AttributeError or similar, which is how a test that
calls the code wrongly fails; only 9 reached the spec checker and 2 were blamed on the
code. So the gain over static comes from the 14B agents, as in the v1 14B arm (27/55 on
the v1 test split). That the filter is too broad is a finding of this run, not something
tuned on it; see the report for the follow-up.

## Reference arm: Claude as the reviewer

To see how far the local pipeline is from a frontier model, Claude (Opus, through Claude
Code subagents) reviewed the same 8 projects: four separate sessions, each given only a
copy of two projects' code folders (no manifest, hidden tests or reference fix), allowed to
read the code and run the project's tests, asked to report every real problem as JSON. Its
findings ([external-claude-reviews/](external-claude-reviews/)) were scored with the same
matching rule by [scripts/project_benchmark_external.py](../../../../scripts/project_benchmark_external.py)
([test2-external-claude/](test2-external-claude/)), and the 61 new pairs were judged by a
new judge session with the same instructions ([judge/labels-claude-new.json](judge/labels-claude-new.json),
merged in [judge/labels-all.json](judge/labels-all.json)); tables in
[report-with-claude.md](report-with-claude.md).

| | Static | Full (14B, local pipeline) | Claude (reference) |
|---|---|---|---|
| Issues found, judge confirmed | 19/55 (35%) | 28/55 (51%) | 49/55 (89%) |
| ... bug | 5/24 | 13/24 | 24/24 |
| ... security | 3/8 | 4/8 | 8/8 |
| ... architecture | 4/8 | 4/8 | 8/8 |
| ... quality | 7/15 | 7/15 | 9/15 |
| Findings (off every seeded place, on decoys) | 28 (0, 2) | 166 (85, 9) | 103 (38, 5) |

The comparison favors Claude in ways the numbers do not show: the projects were written by
Claude models and the judge is a Claude model, so the reference reviewer shares their way of
seeding and describing problems. It also proposed no fixes, so the fix-safety measures do not
apply to it. It is a ceiling for orientation, not a result of this project.
