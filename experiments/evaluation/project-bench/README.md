# project-bench-v1 results (test split)

Protocol: [docs/evaluation/project-benchmark.md](../../../docs/evaluation/project-benchmark.md).
Freeze: [freeze.json](freeze.json), committed in a072b9f before any review of the test split.

| File | What it is |
|---|---|
| [test-static/](test-static/) | The static arm on the 8 test projects (`run.json`, `records.jsonl`) |
| [test-full/](test-full/) | The full arm (agents on Qwen2.5-Coder-3B-Instruct GGUF q4_k_m) |
| [judge/pairs.jsonl](judge/pairs.jsonl) | The 59 located (issue, finding) pairs, without arm or source |
| [judge/labels.json](judge/labels.json) | The judge's labels (a separate language-model session that saw only the pairs) |
| [report.md](report.md), [report.json](report.json) | The full tables, per project and per fix |

Both runs passed the freeze check (`"frozen": true`) at commit a072b9f. The full run
records `"dirty": true` only because the static run's output folder (untracked results)
was already in the working tree; the frozen code, data, settings and model matched.
7 of 572 model calls failed when the laptop ran out of memory while reloading the model
(pipeline 3, textstats 2, webapp 2).

## Main results (8 projects, 55 seeded issues)

| | Static | Full |
|---|---|---|
| Issues found, judge confirmed | 18/55 (33%, CI 22% to 46%) | 19/55 (35%, CI 23% to 48%) |
| ... bug | 4/24 | 4/24 |
| ... security | 4/8 | 4/8 |
| ... architecture | 4/8 | 4/8 |
| ... quality | 6/15 | 7/15 |
| Issues located (a finding on the lines) | 18/55 | 33/55 |
| Findings | 27 | 155 |
| ... on a seeded issue | 21 | 59 |
| ... on a decoy (certain false alarm) | 6 | 11 |
| ... elsewhere (not judged) | 0 | 85 |
| Fixable issues fixed by the ready fixes | 0/32 | 1/32 |
| Fixable issues fixed by some fix (applied alone) | 0/32 | 4/32 |
| Fixes marked ready | 0 | 1 |
| Ready fixes that break a test | 0 | 0 |
| Median review time | 1.6 s | 347 s |

Paired on the same issues: judge confirmed, the full arm found 1 issue the static arm did
not and missed none it found (exact McNemar p = 1.0); located, 15 more (p = 6.1e-05),
but 14 of those 15 extra locations were findings about something else on the same lines.

## What this says

- With a 3B model on a 4 GB laptop GPU, the agents add almost nothing that is confirmed
  to be the seeded problem: 19 versus 18 of 55. Almost every confirmed find, in both arms,
  comes from the static checks (ruff, the project rules, the index metrics).
- The agents add noise: 128 more findings, 85 of them outside every seeded place and 5
  more on decoys.
- The fix gate holds. Of the 15 proposed fixes that break a visible or keep test when
  applied, 12 were rejected (mostly by the project's tests) and 3 stayed uncertain; none
  was marked ready. The one ready fix (textstats B1) fixes its bug. 4 fixable bugs were
  fixed by some proposed fix, 3 of which the gate held back as uncertain (model_only).
- Bugs that need reading the code against its docstring (24 seeded) were found only when
  a linter rule covers them (4 of 24).

These are small synthetic projects; see the protocol's limits section.

## Model-size arm: Qwen2.5-Coder-14B-Instruct (added after the 3B results)

The same frozen pipeline (code, prompts project-v3, settings, test split) with only the
model changed, run on Kaggle (2 x T4) with
[scripts/project_benchmark_model_arm.py](../../../scripts/project_benchmark_model_arm.py):
`bartowski/Qwen2.5-Coder-14B-Instruct-GGUF`, Q4_K_M, revision 5b379ec4bf71, sha256
2946d28c9e1b. The run passed the freeze check in everything but the model
(`"frozen_except_model": true`); it is a post-hoc arm, not the pre-registered result.
Results in [test-full-14b/](test-full-14b/); the static arm rerun on Linux
([kaggle-14b/test-static-linux/](kaggle-14b/test-static-linux/)) gave the same findings
as on Windows in all 8 projects. The 48 pairs first seen in this arm were judged by a new
judge session with the same instructions ([judge/labels-14b-new.json](judge/labels-14b-new.json));
[judge/labels-all.json](judge/labels-all.json) holds all 107 labels.

| | Static | Full, 3B | Full, 14B |
|---|---|---|---|
| Issues found, judge confirmed | 18/55 (33%) | 19/55 (35%) | 27/55 (49%, CI 36% to 62%) |
| ... bug | 4/24 | 4/24 | 10/24 |
| ... security | 4/8 | 4/8 | 6/8 |
| ... architecture | 4/8 | 4/8 | 4/8 |
| ... quality | 6/15 | 7/15 | 7/15 |
| Findings (off every seeded place) | 27 (0) | 155 (85) | 164 (84) |
| Fixable issues fixed by some fix | 0/32 | 4/32 | 14/32 |
| Fixable issues fixed by the ready fixes | 0/32 | 1/32 | 1/32 |
| Ready fixes that break a test | 0 | 0 | 0 |
| Median review time | 1.6 s | 347 s | 612 s (T4) |

Paired, judge confirmed: 14B found 9 issues static missed and missed none it found
(exact McNemar p = 0.0039); against 3B, 8 more and none fewer (p = 0.0078). Of the 14B
arm's 79 fixes, 27 break a test when applied: 26 were rejected and 1 stayed uncertain,
none ready. 11 fixes that do fix their bug stayed uncertain, most with the reason
`model_only` (no test showed the bug): the spec tests of project-v4 target exactly that.

## Model-size arm: Qwen2.5-Coder-32B-Instruct

Same frozen pipeline and test split, `bartowski/Qwen2.5-Coder-32B-Instruct-GGUF` Q4_K_M
(revision 40b525506a4f, sha256 8e2fd78ff55e) split over 2 x T4; `"frozen_except_model":
true`. All 498 model calls succeeded; in ledger the call budget or time limit was reached.
Results in [test-full-32b/](test-full-32b/); the 26 pairs first seen in this arm were
judged by another new session with the same instructions
([judge/labels-32b-new.json](judge/labels-32b-new.json), merged into
[judge/labels-all.json](judge/labels-all.json)); all four arms in
[report-models.md](report-models.md).

| | Static | 3B | 14B | 32B |
|---|---|---|---|---|
| Issues found, judge confirmed | 18/55 | 19/55 | 27/55 | 27/55 |
| ... bug | 4/24 | 4/24 | 10/24 | 10/24 |
| ... security | 4/8 | 4/8 | 6/8 | 4/8 |
| Findings (off every seeded place) | 27 (0) | 155 (85) | 164 (84) | 103 (48) |
| Fixable issues fixed by some fix | 0/32 | 4/32 | 14/32 | 13/32 |
| Fixes marked ready (and fixing their bug) | 0 | 1 (1) | 1 (1) | 4 (4) |
| Ready fixes that break a test | 0 | 0 | 0 | 0 |
| Median review time | 1.6 s | 347 s | 612 s | 1009 s |

14B and 32B find the same number of issues (each finds 5 the other misses; McNemar
p = 1.0). 32B reports 40% fewer findings, half as many off every seeded place, and has 4
ready fixes, all of which fix their bug; of its fixes that break a test, 9 were rejected
and 1 stayed uncertain.
