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
