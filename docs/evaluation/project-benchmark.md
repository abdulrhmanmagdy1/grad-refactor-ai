# Project review benchmark (project-bench-v1)

This benchmark measures the whole-project review mode: how many known problems it finds,
how often it flags correct code, and whether the fixes it marks ready actually fix the
bugs without breaking anything. The guard-clause study ([protocol.md](protocol.md)) is
unchanged; this is a separate protocol for the newer mode.

Code: `src/refactor_ai/project/benchmark.py` and `scripts/project_benchmark.py`.
Data: `datasets/project_bench/v1/{dev,test}/<project>/`.

## What a benchmark project is

A small Python package with problems written into it on purpose, plus everything needed
to score a review of it:

```text
datasets/project_bench/v1/<split>/<name>/
  manifest.json          where each seeded problem and each decoy is
  project/               what the reviewer sees (zipped and uploaded like a user's project)
    <package>/...        the code, 4 to 8 modules
    tests/test_*.py      visible tests; they pass on this code
    README.md            optional, what the package is for
  hidden/test_hidden.py  hidden tests; the reviewer never sees them
  reference/<package>/... the files changed by a correct fix, complete
```

The hidden tests are copied into the project root as `test_zz_benchmark_hidden.py` only
when the benchmark scores a result, and run in a separate process from the visible tests so
that neither can change the other's state (through a shared mutable default, for example).
Two kinds of hidden test:

- `test_<ISSUE>_<what>`: fails on the project because of that issue, passes with the
  reference fix. Example: `test_B1_restock_accepts_the_exact_limit`.
- `test_keep_<what>`: passes on the project and with the reference fix. These protect
  behaviour that is already correct, including the behaviour of the decoys; a fix that
  makes one fail has broken something.

### manifest.json

```json
{
  "schema_version": 1,
  "name": "inventory",
  "description": "Stock levels, reservations and reorder reports for a small shop.",
  "author": "who wrote it",
  "issues": [
    {
      "id": "B1",
      "category": "bug",
      "kind": "off-by-one",
      "file": "inventory/stock.py",
      "lines": [41, 42],
      "anchor": "if quantity < self.limit:",
      "symbol": "Stock.restock",
      "description": "The docstring says the limit is inclusive but the check rejects it.",
      "fix_hint": "Compare with <= so a restock up to the limit is accepted.",
      "fixable_in_function": true,
      "hidden_tests": ["test_B1_restock_accepts_the_exact_limit"]
    },
    {
      "id": "A1",
      "category": "architecture",
      "kind": "import-cycle",
      "file": "inventory/report.py",
      "lines": [3, 3],
      "anchor": "from inventory.stock import",
      "modules": ["inventory.report", "inventory.stock"],
      "description": "stock imports report to format a warning, report imports stock.",
      "fixable_in_function": false
    }
  ],
  "decoys": [
    {
      "id": "D1",
      "file": "inventory/store.py",
      "lines": [20, 22],
      "anchor": "for item in list(self.items):",
      "why_it_is_fine": "It iterates over a copy, so removing from the list is safe."
    }
  ]
}
```

Fields:

- `id`: `B1`, `B2` ... for bugs, `S1` security, `A1` architecture, `Q1` quality; decoys
  `D1`, `D2`.
- `category`: `bug`, `security`, `architecture` or `quality`.
- `kind`: a short kebab-case label (`off-by-one`, `wrong-operator`, `mutable-default`,
  `path-traversal`, `import-cycle`, `layer-violation`, `duplicated-logic`, ...).
- `file` and `lines`: the seeded place, relative to `project/`, 1-based, inclusive. Keep it
  tight: the line or lines a reviewer should point at. For a problem that is a whole
  function (too long, too deeply nested), use the whole function.
- `anchor`: text copied exactly from inside those lines; validation uses it to catch line
  numbers that drifted.
- `symbol`: the function's qualified name (`function` or `Class.method`), when the place is
  inside one.
- `modules`: architecture issues only, the dotted module names involved.
- `other_locations`: optional extra places (`{"file", "lines"}`), for example the second
  copy of duplicated code.
- `fixable_in_function`: true when a correct fix only changes the function named in
  `symbol`. Exactly these issues have `hidden_tests`, and the reference fixes them.

## Authoring rules

These rules are for whoever writes benchmark projects. The test split is written without
looking at the reviewer: its authors do not read `src/refactor_ai/project/` (other than
running the validator), the review prompts, `docs/architecture/project-review.md` or the
project-review tests.

1. Python 3.11 standard library only; tests use pytest. No network, no real subprocesses,
   no files outside pytest's `tmp_path`. The tests run under a restricted runner that
   blocks subprocesses and sockets, so a hidden test about a shell command replaces
   `subprocess.run` with `monkeypatch` and checks the arguments.
2. One package folder plus `tests/`. 4 to 8 modules, 250 to 600 lines of package code,
   most functions under 40 lines. Code a competent developer could have written: type
   hints, docstrings that state what the code should do, sensible names.
3. Seed 6 to 8 issues per project:
   - 3 bugs: logic errors with a hidden test each. The correct behaviour must be clear
     from the docstring, the README, the names or the plain meaning of the domain, so a
     careful reader can tell the code is wrong. Examples: off-by-one, wrong operator or
     comparison, wrong variable, missing case, wrong default, state not reset, wrong
     rounding, swapped arguments.
   - 1 security problem: path traversal, injection into SQL or a shell command, unsafe
     deserialization, a secret compared with `==`, a predictable token, missing
     permission check. Give it a hidden test when the safe behaviour can be tested.
   - 1 architecture problem: an import cycle, a low-level module importing a high-level
     one, a module that does several unrelated jobs, or the same rule implemented in two
     modules.
   - 1 or 2 quality problems: duplicated code, a function nested four or more levels deep,
     a very long function, dead code, magic numbers repeated across functions.
   - Exactly one of the bug and security issues is a pattern that common linters (ruff,
     bandit, pylint) are known to flag, such as a mutable default argument or
     `shell=True` with a formatted string. The others need reading the code to see.
4. Add 2 decoys: correct code that looks suspicious at first sight (iterating over a copy
   while removing, a parameterized SQL query, `hashlib` used for a checksum, a broad
   `except` that logs and re-raises). Give each decoy a `test_keep_` test where possible.
5. Nothing may point at a seeded problem: no comments like `BUG`, `TODO`, `FIXME`, `hack`,
   `unsafe`, `insecure`, no tell-tale names, no visible test that exercises a seeded bug.
   The visible tests pass on the project as given.
6. Outside the seeded places the code must be clean: the validator runs the review's own
   static checks and every finding must fall on an issue or a decoy. Fix anything else it
   reports (an unused import, a too-complex function you did not mean to seed).
7. The reference fix changes only the functions named by fixable issues.

Validate a project with:

```text
python -m uv run python scripts/project_benchmark.py validate --split test --project <name>
```

It checks the manifest, the places and anchors, that the upload limits accept the project,
that every visible test passes, that every `test_<ISSUE>_` hidden test fails on the
project and every `test_keep_` test passes, that everything passes with the reference fix,
that the reference changes only the named functions, and that no static finding falls
outside the seeded places. A project enters the benchmark only when it reports `ok`.

## Splits

- `dev`: written while the harness was built. Runs on it may change the reviewer (prompts,
  thresholds, budgets); they are development evidence, not results.
- `test`: written by separate authors under the rules above, frozen before any review of
  it runs. Results on it are the reported results.

What the developer saw before the freeze: the test authors' hand-back reports listed each
project's issue ids and kinds (for example "B2 off-by-one in letter_grade"), and the
validator's notes said which issues the static checks find. No review ran on the test
split and no test-split code was read. The changes made after those reports arrived were
each prompted by a dev run and are general: prompt version project-v3 (judges reason
first, finders told that names not shown exist elsewhere), the fix parser that keeps only
the function, and the rule that a fix is ready only with machine evidence. The dev runs
behind them, with the judge's labels:

| Dev run (3 projects, 22 issues) | Located | Judge confirmed | Findings off every seeded place | Ready fixes that break a test |
|---|---|---|---|---|
| static | 7 | 7 | 0 | 0 |
| full, project-v2 | 9 | 6 | 0 | 0 (no ready fixes) |
| full, project-v3 with the evidence rule | 13 | 7 | 22 | 0 (no ready fixes) |

Every issue the judge confirmed on the dev split was found by a static check; the agents'
extra locations were findings about something else on the same lines. The full v3 run
also lost 12 of 198 model calls to the laptop running out of memory while reloading the
model.

### project-bench-v2: spec tests and a second test split

The v1 test results (static 18/55 judge confirmed, full 19/55) showed that bugs which contradict the documentation were found only when a linter rule covers them. Prompt version project-v4 adds the spec tester (see the design document): tests written from the documentation, run on the project, with failing tests judged by a checker. Because v1's test split has been seen, v2 is measured on a new split, `test2`, written by four new authors under the same rules who were also asked not to report their seeded issues, so the developer saw only the validator's ok lines. `test2` is frozen in `experiments/evaluation/project-bench/freeze-test2.json` before any review of it; the dev split stays the place for tuning. v1's records and freeze stay as they are.

The v2 final arm is the full pipeline at project-v4 (with the misuse filter and the spec
checker's README added after the first v4 dev run) on Qwen2.5-Coder-14B-Instruct Q4_K_M
(`configs/model.project.14b.json`), run on Kaggle, because the 14B arm of v1 showed the
3B model is the bottleneck. The static arm is run alongside.

What the developer saw of `test2` before its freeze: the authors' validator lines (which
issue ids the static checks find), and, without asking for it, the repository's automatic
security review of the committed files, which named eleven problems in budget, weatherlog,
payroll, forum, hotel, fleet, enrollment and ticketing (SQL built with f-strings, paths
built from names, a missing ownership check, `random` tokens, an open-ended ban, a mutable
default, accumulators not reset, swapped arguments). No change to the review was made
after that review appeared other than the two prompted by the dev run named above.

### project-bench-v3: mypy, spec-test repair and a third test split

After test2 (judge confirmed: static 19/55, full 28/55, Claude as a reference 49/55),
prompt version project-v5 added mypy to the static checks, the signatures of related
project modules to the spec tester's prompt, and one repair round for spec tests that call
the code wrongly (on test2 the misuse filter had set aside 102 of 111 failing tests); a
security fix also made ruff and mypy run isolated from the uploaded project. On the dev
split v5 and v4.1 (14B) located the same 15 of 22 issues, with no ready fix breaking a test
in either; v5 is the final configuration because it carries the security fix. It is
measured on `test3`, eight projects by four new authors who did not report their seeded
issues, frozen in `experiments/evaluation/project-bench/freeze-test3.json`.

What the developer saw of `test3` before its freeze: the authors' validator lines, and the
repository's automatic security review of the written and committed files, which named
about seventeen of its problems (in orders, rental, voting, helpdesk, pharmacy, gym, crm
and delivery). The review code and prompts were last changed before test3 existed; the only
step between seeing those notices and the freeze was the v5 dev run above.

## Freeze

`scripts/project_benchmark.py freeze` writes `experiments/evaluation/project-bench/
freeze.json`: the hash of every test-split project, the hash of the review code
(`src/refactor_ai/project/*.py`, the GGUF provider and worker, the benchmark script), the
review settings, the model identity (id, revision, GGUF file and sha256, context length)
and the matching tolerance. `run --split test` refuses to start when any of these differ
(`--allow-unfrozen` runs anyway and records `"frozen": false`; such a run is not a
result). A change after the freeze needs a new protocol version or, before any test-split
run, a documented re-freeze.

## Arms

Both arms review each project exactly as an upload with the service's default review
settings and the project's visible tests turned on.

- `static`: no model. ruff, the project rules, the index metrics and the guard-clause
  check; the only fixes are the deterministic guard-clause rewrites.
- `full`: the same plus the agents (architecture reviewer and checker, bug finder,
  quality and security reviewer, finding checker, fixer, fix reviewer) on the pinned
  Qwen2.5-Coder-3B-Instruct GGUF model (q4_k_m), greedy decoding.

## Scoring rules

A finding points at a seeded place when it is in the same file and its lines come within
2 lines of the place (any of the issue's locations). For an architecture issue, an
architecture finding also counts when it names at least two of the issue's modules (or
the only one), or when it is a file-level finding about one of the issue's files.

- Issue located: at least one finding points at it. Reported per category with a 95%
  Wilson interval; "right category" counts the issues located by a finding of the same
  category.
- Issue found (the primary measure): located by a finding that a judge confirmed is about
  this problem. A finding can land on the right lines and be about something else (on the
  first dev run, "loan.isbn is a boolean" landed inside the function with the seeded
  bug), so location alone overcounts. `scripts/project_benchmark.py pairs` exports every
  located (issue, finding) pair across the runs once, keyed by a hash so that the same
  finding in two arms is one pair, in hash order and without the arm or the finding's
  source. A separate judge (a language model given only `benchmark.JUDGE_INSTRUCTIONS`
  and the pairs, never the arms or the review code) labels each pair `same` or not, and
  `report --labels` uses the labels. A located issue whose pairs are not all judged is
  reported as not judged, never as found.
- Findings are split into: on a seeded issue, on a decoy (a false alarm for certain), and
  elsewhere (unlabelled: a false alarm or a real problem nobody seeded; these are listed
  for reading, not counted as either).
- Decoys flagged: decoys with at least one finding on them.
- Each fix with a proposed change is applied alone to the original project and all tests
  run (visible and hidden). Outcome: `resolves` (all hidden tests of some issue now pass,
  nothing broken), `harmful` (a visible or `test_keep_` test that passed now fails, or the
  tests no longer run), `no_effect`.
- The fixes marked ready are then applied together, as a user accepting all of them would.
  Reported: fixable issues resolved by the ready fixes together, ready fixes that are
  harmful (the number that matters most: it should be zero), and correct fixes that the
  checks held back.
- Model findings dropped by the finding checker are scored with the same rule, to see
  whether the checker drops real problems.
- Static and full are compared on the same issues with an exact McNemar test, on judged
  detection and on location.

## Limits

The projects are small and synthetic, written for the benchmark, and their authors are
language models too, which may share blind spots with the reviewer's model. Seeded
problems are cleaner than real ones, and a project that is clean outside the seeded places
is unusual. The judge is a language model as well, judging one pair at a time; its labels
are committed with the results so they can be checked. "Unlabelled" findings (not on any
seeded place) are not judged. The results say how the mode behaves on this kind of code,
not how it would do on a large real codebase.
