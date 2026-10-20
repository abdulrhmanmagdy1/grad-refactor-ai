# Data and evaluation notes

Workstream: data and evaluation (owner Shahd Abdelhay). Wave-1 tasks: T03 related work, T07 curated dataset, T08 splits and leakage, T10 protocol draft, T24 harness skeleton. Written on 2026-10-20 by the coding agent from the files and test results named below. Nothing here is a model evaluation result; no model has been evaluated by this workstream yet.

## Status on 2026-10-20

| Item | Status | Evidence |
|---|---|---|
| T03 related work | Reading table of 15 primary sources, each checked on its official page; one method reference | [related work](../../research/related-work.md), [references](../../references.md) |
| Licenses | MBPP CC-BY-4.0, HumanEval MIT verified on the official pages; team-authored data license pending a team decision | [NOTICE](../../../datasets/guard_clauses/v1/NOTICE.md) |
| T07 dataset | 799 records with trusted reference tests, reproducible byte for byte | [data plan](../../data-and-training/data-plan.md), `datasets/guard_clauses/v1/` |
| T08 splits | 627 / 84 / 88 by source group; no cross-split, pilot or demo near-duplicates; test split frozen | [freeze record](../../../experiments/data/test-split-freeze.json), [curation log](../../../experiments/data/curation-log.json) |
| Demonstration cases | 6 hand-written cases, independent of the dataset | `src/refactor_ai/fixtures/demo_cases.json` |
| T10 protocol | Draft eval-v1, not frozen; targets are set after the validation baseline | [protocol](../../evaluation/protocol.md) |
| T24 harness | Implemented and tested with a stub workflow; plumbing check with the fake provider, real coordinator and real runner | [plumbing record](../../../experiments/evaluation/2026-10-20-harness-plumbing-check.json) |

## Data

Real code rarely has this pattern in a form the task accepts: 4 of 974 MBPP functions, 1 of 164 HumanEval functions and 4 of 2,630 TheAlgorithms/Python functions qualify. The dataset therefore consists of 81 team-authored template families (795 records) plus the 4 qualifying MBPP/HumanEval functions that also yield trustworthy tests (one MBPP function has an unreachable `return` and was dropped). Targets come from the shared deterministic transformation; explanations are generated from the same planning rules and name the conditions that became guard clauses.

Reference tests are produced only by executing trusted code in a curation-only executor (separate process, fixed hash seed, step budget, temporary directory). Each record has 3 to 10 tests (5,168 in total) that execute every return and raise statement and every reachable branch outcome, and detect 95.1% of 10,807 single-point mutants (all mutants that any candidate input detects). The reference transformation reproduced the original's outcome on every usable candidate input of every record (differential test). A test re-executes all committed tests against original and target.

Splits are by source group: 57 training families, 12 validation families and 12 test families drawn one per category, plus the 4 real functions in the test split. Near-duplicates use the Allamanis (2019) identifier/literal Jaccard rule (0.8 set, 0.7 multiset) without the small-function exemption; none were found across splits (highest 0.32), against the 124 code items of the models workstream's pilot fixtures (highest 0.42) or against the demonstration cases (highest 0.24). A family with the same purpose as a pilot function (`flag-parse`, similarity 0.61) was kept in training as a precaution. The test split hash is `b765dbb8ba3c3f76771ed6aa4a05e645372de19751f720805ccfc511d5535b72`, frozen 2026-10-20.

## Evaluation harness

`scripts/evaluate.py` runs arms A to D through the workflow coordinator, meters every provider call itself, rechecks syntax and rubric of each proposal without executing it, records failures, timeouts and harness exceptions as attempts, warms up the runner and model before timing, rotates the arm order per case and never overwrites an existing record file. It refuses the test split without `--i-confirm-frozen-test`, `--protocol-version eval-v1`, a frozen protocol record, the local model and a matching test-split hash. `scripts/report_evaluation.py` produces markdown and CSV tables with explicit denominators, paired exact McNemar tests with Holm adjustment, and dependency-free SVG figures, identically on every run from the same records.

## Commands and checks run

- `python -m uv run python scripts/curate_dataset.py --check`: reproducible.
- `python -m uv run python scripts/validate_dataset.py datasets/guard_clauses/v1/records.jsonl --extended --manifest datasets/guard_clauses/v1/manifest.json --external training/pilot`: passed (230,472 cross-split pairs and 42,656 pilot pairs examined).
- `python -m uv run pytest tests/test_data_committed.py tests/test_data_executor.py tests/test_data_curation.py tests/test_dataset.py tests/test_evaluation_harness.py tests/test_evaluation_report.py`: 63 passed.

## Limitations

The template families share one generator design; held-out families test transfer to unseen domains with similar skeletons (structural similarity to the nearest training record has a median of about 0.36). Real code is a four-case probe and may overlap the base model's pretraining data. Reference tests compare exception types, not messages, and cover only the tested inputs. Comments are not preserved in targets. The team-authored data has no redistribution license yet. The protocol, targets and all model results are still open.
