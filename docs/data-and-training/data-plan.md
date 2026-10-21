# Data preparation plan and record (guard_clauses-v1)

Status: dataset built and test split frozen on 2026-10-20, re-rendered in prompt format refactor-v2 the same day with unchanged cases (see [prompt version change](#prompt-version-change-refactor-v1-to-refactor-v2)), by the data and evaluation workstream (coding agent working for Shahd Abdelhay); pending the owner's inspection and the P2 supervisor review. All numbers below come from [manifest.json](../../datasets/guard_clauses/v1/manifest.json) and [curation-log.json](../../experiments/data/curation-log.json).

## Command and reproducibility

```bash
python -m uv run python scripts/curate_dataset.py --download   # first run: fetch pinned sources into data/raw/
python -m uv run python scripts/curate_dataset.py               # rebuild everything
python -m uv run python scripts/curate_dataset.py --check       # rebuild in memory, compare with the committed files
python -m uv run python scripts/curate_dataset.py --refreeze-rendering "<reason>"  # only for a new prompt format of unchanged frozen cases
python -m uv run python scripts/validate_dataset.py datasets/guard_clauses/v1/records.jsonl --extended \
    --manifest datasets/guard_clauses/v1/manifest.json --freeze experiments/data/test-split-freeze.json \
    --external training/pilot
```

The library code is in `src/refactor_ai/data/`. Seed 20261020 drives every random choice through string-seeded generators; no output depends on dictionary or set iteration order, wall-clock time or the hash seed. Rerunning the command in the working tree that produced the files reproduces `records.jsonl`, `metadata.jsonl`, `manifest.json`, `curation-log.json` and `src/refactor_ai/fixtures/demo_cases.json` byte for byte (checked with `--check`, result "reproducible", 2026-10-20 and 2026-10-21). Only `experiments/data/curation-run.json` (git HEAD, uncommitted sources, Python version) changes between runs. Inputs are the curation code, the seed, the two pinned source files (SHA-256 verified), the demonstration cases and the external fixture files under `training/pilot/` (checked for leakage; their hashes are logged). The manifest stores the SHA-256 of every curation source file, so any change to the curation code shows up as a changed `manifest.json` until the outputs are regenerated.

Up to commit `90462d3`, fresh checkouts did not reproduce two of these files. The curation log stored the SHA-256 of the raw bytes of the three files under `training/pilot/`, hashed with the line endings the working tree had (`functions.py` with CRLF, the other two with LF), so a fresh checkout got other hashes and `--check` reported `curation-log.json` and `manifest.json` (which holds the log's hash) as different. Commit `74daf25` fixed it: `leakage.external_code` now hashes the content with CRLF converted to LF, as every other hash here does, and the two files were regenerated; records, metadata, the demonstration cases and the test split did not change. A fresh clone with CRLF line endings then passed `--check --download` ([clean-clone record](../../experiments/qa/2026-10-21-clean-clone-reproduction.md)).

## Record format

Every line of `datasets/guard_clauses/v1/records.jsonl` has exactly the fields of the dataset-record contract ([contracts](../architecture/contracts.md)): `id`, `source_group`, `split`, `prompt`, `completion`, `license`, `refactoring_type`, `original_code`, `target_code`, `function_name`, `tests` (list of `ReferenceTest`), `source`, `source_url`, `provenance`, `prompt_version` (`refactor-v2`) and `task_version` (1). Record ids are valid reference-case ids (`gc1-<family>-NN`, `gc1-mbpp-task-N`, `gc1-humaneval-95`). Per-record curation details (family, attempt, check layout, nesting depth before and after, guard clauses created, test coverage and mutation metrics, whether the prompt has analysis notes) are in `metadata.jsonl`.

- `prompt` = `task_format.build_refactor_user_prompt(original_code)`; for about half of the training records (309 of 627) it also passes the static findings of `guard_clauses.check_input` as analysis notes, so the adapter also sees the multi-role prompt variant. Rule: a training record gets notes when the first byte of `sha256(f"{seed}:findings:{id}")` is even. Validation and test prompts never have notes.
- `completion` = `task_format.render_refactor_completion(explanation, target_code)`: in refactor-v2 the fenced code block comes first, followed by one `Explanation:` line. Here `target_code` = `guard_clauses.to_guard_clauses(original_code)` and the explanation is generated deterministically from the same planning rules as the transformation (`refactor_ai.data.explain`): it lists the conditionals turned into guard clauses in target order, what each guard does (returns X or raises E) and the measured nesting depth before and after, for example "Turned 3 if/else conditionals into guard clauses: `weight <= 0` raises ValueError, `weight > 25` returns None and ... The remaining logic is dedented, reducing the maximum nesting depth from 2 to 1." A test checks that every condition named in an explanation is an `if` test of the target.

## Sources and licenses

| Source | Records | License (verified 2026-10-20) | Yield |
|---|---|---|---|
| Team template families (81 families, 27 categories) | 795 | `LicenseRef-team-authored-pending`: written for this project by the coding agent on behalf of the team; redistribution license pending a team decision | 1,051 generated variants: 8 duplicates skipped, 5 excluded as `no_opportunity`, 1,038 qualified and all 1,038 got trustworthy tests; the first 11 (train) or 7 (held-out) per family by attempt order were kept, 243 surplus unused |
| MBPP, google-research-datasets/mbpp | 3 | CC-BY-4.0 (Hugging Face card); same file as google-research/google-research `mbpp/mbpp.jsonl` at commit f82046b (Apache-2.0 repository, no data-specific statement) | 4 of 974 passed the task rules (0.41%); 3 kept, task 850 dropped because its inner `return False` is unreachable |
| HumanEval, openai/human-eval | 1 | MIT, Copyright (c) OpenAI (LICENSE file and Hugging Face card openai/openai_humaneval) | 1 of 164 (0.61%) |

Attribution and the MIT notice are in [NOTICE.md](../../datasets/guard_clauses/v1/NOTICE.md). MBPP exclusions: 726 no_opportunity, 234 not a single function, 5 imports, 2 dunder access, 1 nested definition, 1 call to `exit`, 1 try/with. HumanEval exclusions: 120 no_opportunity, 26 not a single function, 8 nested definitions, 6 imports (one also nested), 2 try/with, 1 call to `eval`. Item lists per reason are in the curation log.

Mining a well-maintained repository does not help either: a survey of TheAlgorithms/Python (MIT) at commit 6e03a48 found 4 qualifying functions among 2,630 top-level functions in 1,608 files (0.15%; [survey script](../../experiments/data/survey_repository_yield.py), [result](../../experiments/data/survey-thealgorithms.json)). We therefore use team-authored template families for training and held-out families, plus the few real functions as a separate test probe.

### Template families

Each family (`src/refactor_ai/data/families/`) builds realistic small functions in one domain (shipping, pricing, grading, access control, parsing, scheduling, finance, health, devices, operations and 17 more categories) and varies function and parameter names, constants, docstrings, annotations, raise versus return failures, the order of independent checks, the check layout (continue-when-valid pyramid, error-first `else` nesting, `elif` chains, mixtures), statements between checks, core logic (elif chains, loops, accumulators, both-exit branches) and, for 20% of variants, a subset of the checks (single-guard cases). Originals are printed with the same printer as the targets, but `else:` followed by a nested `if` stays nested (the stock `ast.unparse` would collapse it into `elif`), so an original and its target differ only by the refactoring. Template originals have no comments; a generator argument is printed in parentheses, as `ast.unparse` does.

## Inclusion rules

A candidate is kept only if all of these hold:

1. `guard_clauses.check_input(original).supported` is true and the function name matches.
2. `guard_clauses.rubric(original, to_guard_clauses(original)).passed` is true.
3. Real-source functions read no names other than locals, parameters, builtins and the function itself.
4. Trusted reference tests exist (next section): every return and raise statement of the original executes in the selected tests, and the target gives the same outcome as the original on every usable candidate input (differential test). Execution is measured by traced line numbers. A return or raise that shares its line with other code, as in `if x < 0: raise ValueError(...)`, would count as executed when only the condition ran. The curation code does not reject that layout yet, but no record and no demonstration case has it (checked 2026-10-21).
5. No exact or near-duplicate across splits, against the pilot fixtures or against the demonstration cases (see Leakage).

## Reference tests (curation-only executor)

Candidate inputs come from each family's hand-written value pools (Cartesian product, at most 400 calls, sampled deterministically) and, for real sources, from the source's own test calls plus type-directed variations of them. Expected outcomes are obtained by executing the trusted original, never typed by hand. Execution uses `refactor_ai.data.executor`, a curation-only executor that is never used for user input: a separate `python -S -P` process with a minimal environment (PYTHONHASHSEED fixed, no PYTHONPATH), a fresh temporary working directory that is removed afterwards, the function definition re-executed for every call (no state shared through mutable defaults), a deterministic budget of 200,000 traced lines per call and a wall-clock timeout per batch with per-job retry.

A call is usable when the original returns a value whose `repr` round-trips through `ast.literal_eval` with identical types, or raises from one of its own `raise` statements, with the same outcome under hash seeds 0 and 1. Calls that time out (9), raise from elsewhere (183, for example a `TypeError` inside a comparison) or depend on the hash seed are discarded and counted. Tests are then chosen greedily: the source's own test calls first, then calls that execute uncovered return/raise lines, new branch outcomes (probes on every `if`), distinguish more single-point mutants (comparison off by one, flipped equality or membership, `and`/`or`, dropped `not`, inverted branch, lost exit, dropped clamp or conversion such as `min`, `round`, `abs`; after DeMillo, Lipton and Sayward, 1978) or execute new statements, then calls with not yet represented outcomes up to 8 tests, at least 5 when available and at most 12.

Result over all 799 records: 5,168 tests (3,829 returns, 1,339 raises; 3 to 10 per record), 100% of the 3,536 return/raise statements exercised, 6,549 of 6,556 branch outcomes covered and 10,273 of 10,807 mutants detected (95.1%). All of these measures are taken over the candidate inputs only. The metadata field `branch_outcomes_reachable` counts the outcomes that some candidate input produces, not the outcomes that are actually reachable. A mutant that no candidate input distinguishes counts as undetected, and nothing checks whether it is equivalent. The selected tests cover every branch outcome and detect every mutant that some candidate input reaches. The known gaps below were confirmed on 2026-10-21 by re-executing the committed tests:

- **Untested branch.** The 7 missing branch outcomes are the true side of `if digit > 9:` in the 7 card-checksum records (validation). It is reachable, for example with `'0000000000000050'`, but no candidate input that passes the length check has a digit of 5 or more at a doubled position (every second digit from the right). So `digit = digit - 9` never runs, and a candidate without that line passes every reference test of those records.
- **Undetected mutants that are not equivalent.** Some undetected mutants are equivalent, for example `diff > 0` versus `diff >= 0` after an `abs(diff) < band` check. Others differ only in which `ValueError` is raised, which tests cannot see because `ReferenceExpectation` compares exception types, not messages. Others change behavior on inputs that the value pools never produce, and the committed tests pass them. Examples: `gc1-recipe-scaling-07` (test) without the `round(scaled, 1)` call returns 33.333333333333336 instead of 33.3 for `scale_quantity(100, 1, base_servings=3)`. `gc1-quiz-score-03` (test) with `len(key) >= 0` instead of `len(key) > 0` raises ZeroDivisionError instead of ValueError for `mark_quiz([], ())`. `gc1-savings-goal-01` (train) with `months >= 240` instead of `months > 240` returns None instead of 240 for `months_to_goal(12000, 0, 50)`.
- **Float comparison.** Detection compares return values by exact `repr` and type. The reference runner compares floats with `math.isclose` (relative tolerance 1e-9, see [contracts](../architecture/contracts.md)). With the runner's comparison, 10,240 of the 10,807 mutants (94.8%) are detected. The other 33 dropped a `round(...)` call and differ from the original only by float noise: 26 are in train, 5 in validation and 2 in test. The two test cases are `gc1-freight-quote-01` and `gc1-freight-quote-06`, where a candidate that drops `round(quote, 2)` passes every reference test.

Passing the reference tests is therefore weaker evidence of unchanged behavior for these records than the mutation score suggests. A test re-executes every committed test against the original and the target.

## Splits

| Split | Records | Source groups | Rendered sha256 (refactor-v2) | Case-content sha256 |
|---|---|---|---|---|
| train | 627 | 57 families | `b6a7fc0240c33aba0e06c984f073a94f2056d1e1721c52dd0dd0d29c05e236da` | `e4f075dc28a84bd64b49e2a204cc1e6ea1838ce18c50a0c23e1e8cbcdd6491b0` |
| validation | 84 | 12 families | `d18845b04bf7800ac1db82bc2d93f441253b2a012d9a5cb6f058b0d8a111c2e5` | `b3b44b8f20c7cedd78e11086a7b838677dae19e84e7cbd7c9fc39724c2282601` |
| test (frozen) | 88 | 12 families + 3 MBPP + 1 HumanEval | `27b6d0ece9430ee30a96617949a31e1c71a0a5c0be7187b36bc660d998e95633` | `3a1e6b95ce74dbd1acdd76207eefcead31eeb255cc3b24a1e6d3955f90e75d12` |

The rendered hash covers the records exactly as written (it changes with the prompt format); the case-content hash (`refactor_ai.data.content`) covers ids, split and source fields, original and target code, tests, provenance, explanation text and analysis notes, and does not depend on prompt rendering.

The split ratio is 78.5 / 10.5 / 11.0. Whole source groups go to one split: a template family is one group and every MBPP or HumanEval item is its own group. Twelve validation and twelve test families are drawn with a seeded shuffle, at most one per category while categories remain. Each held-out split therefore has 12 families (template domains) that training never sees, from 12 different categories. Categories themselves are not held out: in each held-out split, 10 of the 12 categories also have training families. For example, the test family freight-quote and the training family customs-duty are both in shipping. Only household and web (validation) and household and security (test) have no training family. Held-out results measure transfer to unseen families, not to unseen categories. Held-out families contribute 7 variants each and training families 11, which bounds evaluation cost while keeping family diversity. All real-source items go to the test split as an out-of-template probe; with n = 4 they support descriptive reporting only, and pretraining overlap with these public benchmarks cannot be excluded for the base model.

- Validation families: blood-pressure, card-checksum, garden-watering, http-status, income-tax, meeting-end, parcel-shipping, parking-fee, retry-backoff, scholarship, version-parse, warehouse-bin.
- Test families: atm-withdrawal, course-enrollment, email-split, freight-quote, hotel-booking, invoice-status, login-attempt, quiz-score, recipe-scaling, reset-token, text-truncate, tracking-status.
- The family `flag-parse` is pinned to training: it implements the same idea as `parse_bool` in the models workstream's pilot fixtures (identifier/literal Jaccard 0.61, below the near-duplicate threshold), so it was kept out of held-out splits as a precaution.

## Leakage checks

- **Exact duplicates.** Normalized prompts and ast-normalized originals are unique across the whole dataset; normalized targets and completions may repeat only inside one split (two nesting styles of one function legitimately share a target). Result: no duplicates.
- **Near-duplicates across splits.** Criterion of Allamanis (2019): two functions are near-duplicates when the Jaccard similarity of their identifier and literal token sets is at least 0.8 and that of the multisets at least 0.7, computed on ast-normalized originals and, separately, targets. Unlike that paper, small functions are not exempted, which makes the rule stricter for this dataset. A flagged pair would remove the record in the earlier split (train before validation before test). Result: 115,236 cross-split pairs per field examined, none flagged; highest set similarity 0.32 (train-validation) and 0.25 (test).
- **Structure (reported, not enforced).** Every record applies the same refactoring, so similar skeletons across splits are expected. Jaccard similarity of 4-gram shingles over the token sequence with names, strings and numbers abstracted, nearest training record: validation median 0.37 (maximum 0.59), test median 0.36 (maximum 0.59) on originals.
- **Pilot fixtures.** All functions found in `training/pilot/` (124 code items in 3 files at curation time, file hashes logged) were compared with every validation and test record: 42,656 pairs, none flagged, highest set similarity 0.42, no pair at or above the 0.5 watch level. The models workstream must not add fixtures that near-duplicate the frozen test split; `--check` and `tests/test_data_committed.py` fail if one appears.
- **Demonstration cases.** Compared with all 799 records: 19,176 pairs, highest set similarity 0.24, no exact matches.

## Manual sample review

Twenty records (10 train, 4 validation, 6 test including 2 MBPP; seeded, one per family) were read in full on the final dataset; every expected value was traced by hand. The review found two problems that were fixed before the freeze: a grammatical error in explanations with one unlisted guard, and tests that did not exercise a capped or rounded return value (fixed by the clamp mutants and outcome-diversity selection). What was checked and the per-record notes are in [manual-inspection-2026-10-20.md](../../experiments/data/manual-inspection-2026-10-20.md).

## Test-split freeze

[test-split-freeze.json](../../experiments/data/test-split-freeze.json) records the 88 test ids, two hashes (the case-content hash `3a1e6b95…`, which must never change, and the rendered split hash `27b6d0ec…` of the current prompt version), the prompt version, the freeze date 2026-10-20, the curation command, seed, the hashes of the curation code and the history of earlier freezes. The curation command refuses any output with other test ids or other case content. An output that changes only the rendering is refused unless `--refreeze-rendering` gives a reason; the previous freeze then moves to the history. The validator and the evaluation harness check both hashes, and the harness refuses the test split without an explicit confirmation flag and a frozen protocol. Nobody may train, tune prompts, select models or set targets on the test split; a change of cases requires a new dataset version and a new evaluation protocol version.

## Prompt version change (refactor-v1 to refactor-v2)

On 2026-10-20 the coordinator adopted prompt format refactor-v2 (code block first, then one `Explanation:` line), selected on 24 validation records only: the base model parsed 2 of 24 with refactor-v1 and 24 of 24 with refactor-v2 ([selection record](../../experiments/models/2026-10-20-prompt-format-selection.md)). No model or person had been evaluated on the test split. The dataset was rebuilt with the same command and re-frozen with the reason "prompt rendering changed from refactor-v1 to refactor-v2 on validation-only evidence before any test evaluation; test case content unchanged, see content_sha256".

A record-by-record comparison with the committed refactor-v1 file (commit 446db35) is in [2026-10-20-refactor-v2-regeneration.json](../../experiments/data/2026-10-20-refactor-v2-regeneration.json): all 799 records keep their ids and order, every field other than `prompt`, `completion` and `prompt_version` is byte-identical, each new prompt and completion contains exactly the same lines as before in a different order, and the case-content hashes of all three splits are unchanged. `metadata.jsonl` and the demonstration cases are byte-identical. Rendered hashes changed as follows: records file `6c586c71…` to `299b4f7f…`; train `dc4ac534…` to `b6a7fc02…`; validation `4b8c7625…` to `d18845b0…`; test `b765dbb8…` to `27b6d0ec…`. The refactor-v1 freeze is kept in the freeze record's history, together with a note on the two pre-commit wave-1 freezes (`164ce75e…`) that were superseded when the reference tests were strengthened.

## Sizes and limits

`records.jsonl` is 3.5 MB (799 lines). Prompt plus completion length: median 1,841 characters in training (90th percentile 2,300, maximum 2,696); the longest record overall (HumanEval/95, test) has 3,327 characters. The training configuration's `max_length` must cover the longest training record after tokenization; check it with `training/train_lora.py --check-data` rather than estimating.

Known limitations: template families share one generator style despite their variation; real code is a 4-record probe; exception messages are not compared by reference tests, and the reference tests have the gaps listed under [reference tests](#reference-tests-curation-only-executor); comments are not preserved in targets; NaN inputs are out of scope for the transformation and never appear in tests; the team-authored data has no redistribution license yet.

The provenance of `gc1-humaneval-95` says "line endings and trailing spaces normalized", but two lines of its code still end in a space. Removing the spaces would change the docstring, and `sources.normalize_source_code` removes trailing spaces only when the whole syntax tree stays the same. In fact only the line endings were normalized and the leading blank lines removed, as NOTICE.md says. The provenance is part of the frozen case content, so it stays unchanged in v1.

Several defects in the curation code are still open, because any code change means regenerating the committed outputs (the manifest holds the code hashes):

- Fixed in `74daf25`: the pilot file hashes depended on line endings; see [command and reproducibility](#command-and-reproducibility).
- Return and raise coverage is measured by line; see [inclusion rules](#inclusion-rules).
- Without `--check`, the command writes `src/refactor_ai/fixtures/demo_cases.json` before the demonstration-overlap and freeze checks run. A refused run can therefore leave a changed demonstration file behind; restore it with `git checkout -- src/refactor_ai/fixtures/demo_cases.json`.
- `freeze_record` and `refrozen_record` write the fixed date 2026-10-20 (`FREEZE_DATE`) into `frozen_on`, `rendering_refrozen_on` and `superseded_on`. A later freeze or re-freeze would carry that date until the code uses the actual date.

## GitHub storage

The dataset, metadata, manifest and curation log total about 4.4 MB of text and are committed. Raw downloads stay in the ignored `data/raw/` folder and are re-fetched from pinned URLs with SHA-256 checks.
