# Data preparation plan and record (guard_clauses-v1)

Status: dataset built and test split frozen on 2026-10-20 by the data and evaluation workstream (coding agent working for Shahd Abdelhay); pending the owner's inspection and the P2 supervisor review. All numbers below come from [manifest.json](../../datasets/guard_clauses/v1/manifest.json) and [curation-log.json](../../experiments/data/curation-log.json).

## Command and reproducibility

```bash
python -m uv run python scripts/curate_dataset.py --download   # first run: fetch pinned sources into data/raw/
python -m uv run python scripts/curate_dataset.py               # rebuild everything
python -m uv run python scripts/curate_dataset.py --check       # rebuild in memory, compare with the committed files
python -m uv run python scripts/validate_dataset.py datasets/guard_clauses/v1/records.jsonl --extended \
    --manifest datasets/guard_clauses/v1/manifest.json --freeze experiments/data/test-split-freeze.json \
    --external training/pilot
```

The library code is in `src/refactor_ai/data/`. Seed 20261020 drives every random choice through string-seeded generators; no output depends on dictionary or set iteration order, wall-clock time or the hash seed. Rerunning the command reproduces `records.jsonl`, `metadata.jsonl`, `manifest.json`, `curation-log.json` and `src/refactor_ai/fixtures/demo_cases.json` byte for byte (checked with `--check`, result "reproducible", 2026-10-20). Only `experiments/data/curation-run.json` (git HEAD, uncommitted sources, Python version) changes between runs. Inputs are the curation code, the seed, the two pinned source files (SHA-256 verified), the demonstration cases and the external fixture files under `training/pilot/` (checked for leakage; their hashes are logged).

## Record format

Every line of `datasets/guard_clauses/v1/records.jsonl` has exactly the fields of the dataset-record contract ([contracts](../architecture/contracts.md)): `id`, `source_group`, `split`, `prompt`, `completion`, `license`, `refactoring_type`, `original_code`, `target_code`, `function_name`, `tests` (list of `ReferenceTest`), `source`, `source_url`, `provenance`, `prompt_version` (`refactor-v1`) and `task_version` (1). Record ids are valid reference-case ids (`gc1-<family>-NN`, `gc1-mbpp-task-N`, `gc1-humaneval-95`). Per-record curation details (family, attempt, check layout, nesting depth before and after, guard clauses created, test coverage and mutation metrics, whether the prompt has analysis notes) are in `metadata.jsonl`.

- `prompt` = `task_format.build_refactor_user_prompt(original_code)`; for about half of the training records (309 of 627) it also passes the static findings of `guard_clauses.check_input` as analysis notes, so the adapter also sees the multi-role prompt variant. Rule: a training record gets notes when the first byte of `sha256(f"{seed}:findings:{id}")` is even. Validation and test prompts never have notes.
- `completion` = `task_format.render_refactor_completion(explanation, target_code)`, where `target_code` = `guard_clauses.to_guard_clauses(original_code)` and the explanation is generated deterministically from the same planning rules as the transformation (`refactor_ai.data.explain`): it lists the conditionals turned into guard clauses in target order, what each guard does (returns X or raises E) and the measured nesting depth before and after, for example "Turned 3 if/else conditionals into guard clauses: `weight <= 0` raises ValueError, `weight > 25` returns None and ... The remaining logic is dedented, reducing the maximum nesting depth from 2 to 1." A test checks that every condition named in an explanation is an `if` test of the target.

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
4. Trusted reference tests exist (next section): every return and raise statement of the original executes in the selected tests, and the target gives the same outcome as the original on every usable candidate input (differential test).
5. No exact or near-duplicate across splits, against the pilot fixtures or against the demonstration cases (see Leakage).

## Reference tests (curation-only executor)

Candidate inputs come from each family's hand-written value pools (Cartesian product, at most 400 calls, sampled deterministically) and, for real sources, from the source's own test calls plus type-directed variations of them. Expected outcomes are obtained by executing the trusted original, never typed by hand. Execution uses `refactor_ai.data.executor`, a curation-only executor that is never used for user input: a separate `python -S -P` process with a minimal environment (PYTHONHASHSEED fixed, no PYTHONPATH), a fresh temporary working directory that is removed afterwards, the function definition re-executed for every call (no state shared through mutable defaults), a deterministic budget of 200,000 traced lines per call and a wall-clock timeout per batch with per-job retry.

A call is usable when the original returns a value whose `repr` round-trips through `ast.literal_eval` with identical types, or raises from one of its own `raise` statements, with the same outcome under hash seeds 0 and 1. Calls that time out (9), raise from elsewhere (183, for example a `TypeError` inside a comparison) or depend on the hash seed are discarded and counted. Tests are then chosen greedily: the source's own test calls first, then calls that execute uncovered return/raise lines, new branch outcomes (probes on every `if`), distinguish more single-point mutants (comparison off by one, flipped equality or membership, `and`/`or`, dropped `not`, inverted branch, lost exit, dropped clamp or conversion such as `min`, `round`, `abs`; after DeMillo, Lipton and Sayward, 1978) or execute new statements, then calls with not yet represented outcomes up to 8 tests, at least 5 when available and at most 12.

Result over all 799 records: 5,168 tests (3,829 returns, 1,339 raises; 3 to 10 per record), 100% of the 3,536 return/raise statements exercised, 6,549 of 6,556 branch outcomes covered (all reachable ones), 10,273 of 10,807 mutants detected (95.1%; every mutant that any candidate input detects is detected by the selected tests). The remaining mutants are equivalent (for example `diff > 0` versus `diff >= 0` after an `abs(diff) < band` check) or differ only in which `ValueError` is raised, which tests cannot see because `ReferenceExpectation` compares exception types, not messages. A test re-executes every committed test against the original and the target.

## Splits

| Split | Records | Source groups | sha256 |
|---|---|---|---|
| train | 627 | 57 families | `dc4ac5348ac13613155f933098f0d9d53da64b063076a01ccf6f7fe65454d9be` |
| validation | 84 | 12 families | `4b8c76255b6e88669715990bb4c1b83a829b5add41d1b63691929352885fe848` |
| test (frozen) | 88 | 12 families + 3 MBPP + 1 HumanEval | `b765dbb8ba3c3f76771ed6aa4a05e645372de19751f720805ccfc511d5535b72` |

The split ratio is 78.5 / 10.5 / 11.0. Whole source groups go to one split: a template family is one group and every MBPP or HumanEval item is its own group. Twelve validation and twelve test families are drawn with a seeded shuffle, at most one per category while categories remain, so each held-out split covers 12 domains that training never sees. Held-out families contribute 7 variants each and training families 11, which bounds evaluation cost while keeping family diversity. All real-source items go to the test split as an out-of-template probe; with n = 4 they support descriptive reporting only, and pretraining overlap with these public benchmarks cannot be excluded for the base model.

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

[test-split-freeze.json](../../experiments/data/test-split-freeze.json) records the 88 test ids, the split hash above, the freeze date 2026-10-20, the curation command, seed and the hashes of the curation code. The curation command refuses to write any output that would change the frozen test split, and the evaluation harness refuses the test split without an explicit confirmation flag, a frozen protocol and a matching hash. Nobody may train, tune prompts, select models or set targets on the test split; a change requires a new dataset version and a new evaluation protocol version.

## Sizes and limits

`records.jsonl` is 3.5 MB (799 lines). Prompt plus completion length: median 1,841 characters in training (90th percentile 2,300, maximum 2,696); the longest record overall (HumanEval/95, test) has 3,327 characters. The training configuration's `max_length` must cover the longest training record after tokenization; check it with `training/train_lora.py --check-data` rather than estimating.

Known limitations: template families share one generator style despite their variation; real code is a 4-record probe; exception messages are not compared by reference tests; comments are not preserved in targets; NaN inputs are out of scope for the transformation and never appear in tests; the team-authored data has no redistribution license yet.

## GitHub storage

The dataset, metadata, manifest and curation log total about 4.4 MB of text and are committed. Raw downloads stay in the ignored `data/raw/` folder and are re-fetched from pinned URLs with SHA-256 checks.
