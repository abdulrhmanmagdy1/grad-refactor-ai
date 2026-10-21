# Evaluation protocol eval-v1 (frozen)

Status: **frozen on 2026-10-21, before any test-split run** (data and evaluation workstream, coding agent working for Shahd Abdelhay; pending the owner's review). The freeze record is [`experiments/evaluation/protocol-freeze.json`](../../experiments/evaluation/protocol-freeze.json); the executable part is `src/refactor_ai/evaluation/protocol.py` (arms, settings, test-split guard) and `src/refactor_ai/evaluation/targets.py` (numerical targets). No evaluation record of the test split exists: the repository's evaluation outputs and Kaggle submissions hold validation and plumbing runs only. Any change to arms, budgets, generation settings, prompts, measures, data, model or frozen code after the freeze needs a new protocol version (eval-v2) and is reported as exploratory; only before any test-split run may the freeze be redone, with the previous record kept in its `history` and the reason stated.

## Questions and comparisons

The comparison separates the effect of fine-tuning from the effect of role coordination on one task (`guard_clauses`, task version 1, prompt `refactor-v2`: the fenced code first, then one `Explanation:` line; selected on validation records only).

| Arm | Model configuration | Workflow | WorkflowSettings |
|---|---|---|---|
| A | Original model | Refactoring role only | `mode=single_role`, `refactor_use_adapter=false`, `max_calls=1`, `max_corrections=0` |
| B | Original model | Analysis, refactoring and review, at most one correction | `mode=multi_role`, `refactor_use_adapter=false`, `max_calls=5`, `max_corrections=1` |
| C | LoRA adapter on the refactoring role | Refactoring role only | `mode=single_role`, `refactor_use_adapter=true`, `max_calls=1`, `max_corrections=0` |
| D | LoRA adapter on the refactoring role; analysis and review on the original model | Analysis, refactoring and review, at most one correction | `mode=multi_role`, `refactor_use_adapter=true`, `max_calls=5`, `max_corrections=1` |

Pre-declared paired comparisons on the same cases: B vs A (coordination, original model), C vs A (fine-tuning, single role), D vs C (coordination, adapted role) and D vs B (fine-tuning, multi-role).

## Model and hardware

- Base model `Qwen/Qwen2.5-Coder-0.5B-Instruct` at revision `ea3f2471cf1b1f0db85067f1ef93848e38e88c25`.
- Adapter `full-2026-10-21`: `adapter_model.safetensors` SHA-256 `dff9ae024f0314224d84759772918b59a3fa9037ecbf7ad7a7d43357e1b1d5d2`, `adapter_config.json` SHA-256 `a190572935f3c37d2f22fcca45024c4fb4f790e3f99802457abc2d3f38682571`. It was trained on the 627 training records only ([training record](../../experiments/training/full-2026-10-21.json)) and is used by the refactoring role of arms C and D only.
- Inference on Kaggle through the project's lane (`training/kaggle/lane.py`, machine shape NvidiaTeslaT4): one Tesla T4 (cuda:0, compute capability 7.5), **float32** (the T4 has no native bfloat16; training also used fp32), torch 2.11.0+cu128, CUDA 12.8, driver 580.178.04, Python 3.13.15, transformers 5.20.2, peft 0.21.2, accelerate 1.15.0, with Kaggle's preinstalled torchao removed. The test run uses the same lane, machine shape, device and dtype; latency and memory are comparable only on this hardware. Greedy decoding on a GPU is deterministic in practice but not guaranteed bit for bit across runs.

## Fixed settings (identical for every arm)

- Generation: greedy decoding (`temperature=0`, `top_p=1`), `seed=42`, `max_input_tokens=2048`, `timeout_s=120` per call; `max_new_tokens` 384 for analysis, 768 for refactoring and 384 for review. Run timeout 600 s per case; budgets as in the table. The freeze record stores the full WorkflowSettings of each arm, equal to the validation run's `run.json`.
- **These are the harness settings, not the service's interactive defaults.** The application's defaults (`WorkflowSettings()` in `contracts.py`) are analysis 384 new tokens, 2048 input tokens, 60 s; refactoring 1024, 2048, 120 s; review 768, 4096, 90 s. The protocol does not use them, for three reasons. The harness budgets were declared in the draft protocol when the harness was added (commit 446db35, 2026-10-20), before any model run, while the service defaults were set later that day (commit f8dc49c) for interactive use on the demonstration laptop. The validation baseline, and with it every numerical target, was measured with the harness settings, so the test run must use them to be comparable. And stating the settings in the protocol means a later change to the application cannot silently change the evaluation. Consequence: results describe the workflow under these budgets. In the validation run 87 of 260 review outputs reached the 384-token review limit (B 58 of 161, D 29 of 99); every one began with an accept verdict and was repeating the same reason or sentence when cut, so it could not be parsed and the review counted as an error. This produced 21 of D's 23 uncertain cases; 31 of B's 84 cases also ended with such a review. A larger budget may only lengthen these loops; that was not tested. 3 of 430 refactoring outputs and none of the 168 analysis outputs reached their limits; the longest prompt had 743 tokens and the slowest call took 20.9 s.
- Prompts: analysis-v1, refactor-v2, correction-v2 (which embeds refactor-v2) and review-v1, as implemented in the frozen code.
- The harness counts every provider call itself and flags any call beyond `max_calls` or any adapter flag that does not match the arm.
- The trusted reference runner from the verification workstream (`refactor_ai.verification.create_runner("auto")`) runs each case's reference tests; when its isolation checks fail, tests are `not_run` and never count as a pass.
- Before timing, the harness runs the runner's self-checks and one untimed warm-up generation per adapter state (recorded in the run manifest). When an attempt ends with the model worker stopped (a generation timeout or a worker crash), the untimed warm-up runs again before the next attempt, so the model reload is not charged to another case; each re-warm-up is listed in the manifest summary (`rewarm`). The arm order rotates from case to case so no arm always runs first.
- One attempt per (case, arm). A run interrupted by infrastructure may be resumed for missing attempts only, with `--resume --evaluation-id <id>` (the id is printed when the run starts; `--resume` without the id, or for an id without records, is refused). Completed attempts are never repeated to obtain a better outcome. If an interrupted write left an unterminated last line in `records.jsonl`, the resumed run moves those bytes to `records.jsonl.partial-at-byte-<offset>` (kept, not deleted), lists the move in the manifest summary (`repaired_last_line`), and attempts that case again because its record was never written.

### Oracle feedback in arms B and D (disclosure)

In arms B and D the single correction is requested when the first proposal fails syntax, the rubric or the reference tests, or the review rejects it. The correction prompt (correction-v2) lists the problems found by the application, including "Reference tests: k of n passed" and up to three failing reference tests, each with the call, its arguments and the expected return value or exception. These are the evaluation's own reference tests. B and D therefore receive test-oracle feedback that A and C never receive and that a user's own code does not have (the service runs reference tests only for a chosen reference case). Their reference-test and acceptance rates after a correction are optimistic for real use, and B vs A and D vs C measure role coordination together with this feedback. On validation a correction ran in 79 of 84 B cases and 15 of 84 D cases.

## Data

- Baseline, prompt checks and adapter selection: the validation split (84 cases from 12 unseen families).
- Final comparison: the frozen test split, 88 cases (12 unseen template families plus 3 MBPP and 1 HumanEval functions, 16 source groups), dataset SHA-256 `299b4f7fca170d2a9260319f6c1f81e832d54114c8bdd51959d6aeb8b23ff2e3`, case-content hash `3a1e6b95ce74dbd1acdd76207eefcead31eeb255cc3b24a1e6d3955f90e75d12` and refactor-v2 rendered hash `27b6d0ece9430ee30a96617949a31e1c71a0a5c0be7187b36bc660d998e95633` ([test-split freeze record](../../experiments/data/test-split-freeze.json)). The four real-source cases are also reported separately; pretraining overlap with these public benchmarks cannot be excluded.

## Test-split guard

`scripts/evaluate.py` refuses the test split unless `--i-confirm-frozen-test` and `--protocol-version eval-v1` are given, the provider is the local model, and `protocol.check_protocol_freeze()` finds no difference between the freeze record and the run:

- `protocol_version` is `eval-v1` and `status` is `frozen`;
- the stored settings of arms A, B, C and D equal the harness settings exactly;
- the `model` object names `model_id`, `model_revision`, `adapter_id` and a SHA-256 `adapter_sha256`;
- the dataset hash, the test split's rendered hash, case-content hash and case count equal the recorded ones, and the test-split freeze record, when present, agrees with them;
- every file of the frozen code has the recorded SHA-256 (CRLF read as LF), with no file missing or added. The frozen code is `scripts/evaluate.py`, `scripts/report_evaluation.py`, `src/refactor_ai/agents/`, `contracts.py`, `src/refactor_ai/evaluation/`, `providers/local.py`, `providers/model_worker.py`, `task_format.py`, `src/refactor_ai/tasks/` and `src/refactor_ai/verification/` (29 files at the freeze).

Any other record is refused, with every difference named. The single test run covers every test case, so `--limit`, `--case-ids` and `--runner disabled` are refused. After the warm-up and before the first attempt, the run also stops if the reference runner is not enabled, if a warm-up call failed (for example a missing adapter), or if a warm-up call reports a model identity other than the record's `model` object (adapter fields are compared for adapter calls). `tests/test_evaluation_freeze.py` checks that the committed record is accepted and agrees with the training record, the validation evidence and the targets rule.

## Measures and denominators

N is the number of attempted cases of an arm (88 per arm on the test split). Every rate uses N as its denominator, so failures, timeouts and harness exceptions count as non-success; nothing missing is counted as zero. A measurement that could not be taken is null with a reason in the record. A failed run has no final proposal, so its syntax, rubric and reference-test outcomes are `not_run` and never count as a success, even when the workflow had checked its last proposal before the failure (for example when the review call timed out in arm B or D).

| Measure | Definition |
|---|---|
| Overall acceptance (primary) | Disposition `proposal_ready`: syntax and rubric pass, reference tests pass, and the review accepts (B, D) or is not run (A, C) |
| Syntax validity | The run completed and its final proposal parses (`ast.parse`) |
| Rubric success | The run completed and `guard_clauses.rubric` passes (structure only, not behavior) |
| Reference-test pass | The run completed and all reference tests pass; also reported over the cases whose tests executed, meaning at least one test produced a result (a runner error that ran no test, such as a test process that could not start, is not an execution) |
| Failure rate | Run status `failed` or harness exception, by failure type |
| Timeout rate | Provider timeout or run timeout |
| Rejected, uncertain, no change | Dispositions, each over N |
| Latency | Wall-clock time of the whole workflow per case: median, 90th percentile (nearest rank), mean |
| Calls and tokens | Provider calls per case (harness count) and prompt plus completion tokens when the provider reports them |
| Memory | Peak working set of the model worker process and GPU memory used after the case (nvidia-smi), when measurable |
| Recheck agreement | The harness rechecks syntax and rubric of each final proposal and reports disagreements with the workflow |

Paired comparisons count, over cases attempted by both arms, how many cases each arm accepts that the other does not, with the two-sided exact McNemar p-value and a Holm adjustment over the four comparisons (alpha 0.05). Rates come with their counts. Cases come from 16 source groups, so cases are not independent; results are reported by family as well, and conclusions are limited to this task, these cases and this model. Passing reference tests supports behavior preservation only on the tested inputs. Exception messages are not compared by the tests.

## Case-level record

`scripts/evaluate.py` writes one JSON line per (case, arm) to `runs/evaluation/<evaluation-id>/records.jsonl`, validated by `refactor_ai.evaluation.records.EvaluationRecord`:

- identity: `evaluation_id`, `protocol_version`, `protocol_status`, `arm`, `order_position`, `case_id`, `split`, `source`, `source_group`, `dataset_sha256`, `split_sha256`, `code_sha` (Git HEAD, or on Kaggle the commit in the bundle manifest), `started_at`, `evaluator`;
- model: `provider_mode`, `model`, `models_used` (every distinct model identity reported per call), `settings` (full WorkflowSettings), `generation_seed`;
- input and output: `input_sha256`, `output_sha256`, `proposed_code`, `explanation`, and per call the role, adapter flag, model, elapsed time, token counts, finish reason, error code and raw output (`calls`);
- outcome: `run_status`, `disposition`, `disposition_reasons`, `stop_reason`, `error`, `failure_type`, `syntax`, `rubric`, `rubric_failed_checks`, `reference_tests` (status and counts), `model_review`, `recheck`, `proposal_ready`;
- cost: `attempt_count`, `reported_call_count`, `call_count`, `calls_by_role`, `prompt_tokens`, `completion_tokens`, `latency_s`, `stage_timings`, `worker_peak_rss_mb`, `gpu_memory_used_mb`;
- `null_reasons` and `warnings` (for a failed run whose workflow had checked its last proposal, a `failed_run_checks:` warning keeps those statuses for error analysis).

Each record is one LF-terminated line; U+0085, U+2028 and U+2029 inside strings are written as JSON escapes, and readers split on LF only. A run manifest stores the command, arms and settings, dataset identity, case ids, provider and runner information, warm-up results, the test-split authorization evidence (the full freeze record) and the run summary. It is written after the warm-up (so an interrupted segment keeps one) and again when the segment ends. The first segment writes `run.json`; each resumed segment writes its own `run-<UTC time>.json` and lists the earlier manifests, so no segment's manifest is overwritten. Tables and figures are produced only from the records: `python -m uv run python scripts/report_evaluation.py <records.jsonl> --out <directory> [--targets experiments/evaluation/protocol-freeze.json]` (summary.md, CSV tables, report.json and SVG figures; with `--targets` also `targets.csv`, `target_directions.csv` and a summary section assessing the targets below).

## Validation baseline

The four arms ran once on the 84 validation cases on Kaggle on 2026-10-21 (kernel `grad-refactor-ai-eval-600603dc`, about 75 minutes of evaluation). The kernel outputs are kept byte for byte, with their provenance and the code check below, in [`experiments/evaluation/validation-2026-10-21/`](../../experiments/evaluation/validation-2026-10-21/provenance.json).

| Measure (over 84) | A | B | C | D |
|---|---|---|---|---|
| Overall acceptance (proposal_ready) | 6 | 3 | 69 | 46 |
| Syntax validity | 83 | 84 | 84 | 84 |
| Rubric success | 17 | 16 | 84 | 84 |
| Reference tests pass | 66 | 69 | 69 | 69 |
| Run failed | 1 (unparseable output) | 0 | 0 | 0 |
| Uncertain | 0 | 2 | 0 | 23 |
| Latency median (s) | 4.08 | 15.54 | 9.74 | 15.81 |
| Calls per case | 1.00 | 4.86 | 1.00 | 3.36 |

Paired comparisons (proposal_ready; first-arm-only / second-arm-only cases, Holm-adjusted p): B vs A 2 / 5, p = 0.45; C vs A 65 / 2, p < 1e-15; D vs C 2 / 25, p = 1.1e-5; D vs B 44 / 1, p < 1e-10.

**Code used for the baseline.** The validation bundle was built from commit ee87a11 with uncommitted changes; every file equals ee87a11 except `verification/runner.py` (the version later committed in f187b63) and the kernel template. The frozen code includes the later fixes of f187b63 and e4d6f31: the rubric no longer counts a trailing `elif` as a guard clause, the JSON repair and the unfenced-code repair changed, static findings mirror the rewrite, the test admission policy also refuses `getattr`, `hasattr`, `setattr` and `delattr` used as values, failed runs never count checks as successes, and the report gates successes on completed runs. `check_code_changes.py` in the evidence folder replays every deterministic decision of the 336 records with both code versions without a model: the current report code reproduces every table of the Kaggle report, and no outcome of A, C or D changes. In B, `gc1-blood-pressure-01` and `gc1-blood-pressure-05` (recorded proposal_ready) now fail the rubric's guard-clause check and would receive a correction, and `gc1-http-status-07` (recorded rejected) would receive a different correction prompt, so these three B outcomes are undetermined under the frozen code: B's attainable validation counts are 1 to 4 accepted, 81 to 84 syntax-valid and 0 to 3 failed. The earlier harness defects fixed in e4d6f31 did not affect this run: it had no failed run in B, C or D, A's one failure (output cut off at 768 tokens) was already scored as not run, no runner error ran zero tests, and no model worker stopped.

## Numerical targets (set before any test-split run)

Rule (also in `targets.py` and the freeze record): for every arm, the floor for overall acceptance and for syntax validity is the lower limit of the two-sided 95 % Clopper-Pearson interval of the validation proportion, and the ceiling for the failure rate is the upper limit of that interval. Where a validation count is undetermined under the frozen code, a floor uses the smallest and a ceiling the largest attainable count. Limits are rounded to six decimals in the arm's favour. A floor is met when the test rate over all 88 attempted cases is at least the limit; a ceiling when it is at most the limit.

| Arm | Validation accepted | Acceptance floor | Validation syntax-valid | Syntax floor | Validation failed | Failure ceiling |
|---|---|---|---|---|---|---|
| A | 6 | >= 2.67% (at least 3 of 88) | 83 | >= 93.54% (at least 83 of 88) | 1 | <= 6.46% (at most 5 of 88) |
| B | 1-4 | >= 0.03% (at least 1 of 88) | 81-84 | >= 89.92% (at least 80 of 88) | 0-3 | <= 10.08% (at most 8 of 88) |
| C | 69 | >= 72.26% (at least 64 of 88) | 84 | >= 95.70% (at least 85 of 88) | 0 | <= 4.30% (at most 3 of 88) |
| D | 46 | >= 43.52% (at least 39 of 88) | 84 | >= 95.70% (at least 85 of 88) | 0 | <= 4.30% (at most 3 of 88) |

Expected directions: for each paired comparison, the sign of the validation difference when its Holm-adjusted exact McNemar p-value is below 0.05 for every attainable validation outcome (all 8 outcomes of B's three undetermined cases were checked); otherwise none. On the test split a direction is confirmed when the difference has that sign with a Holm-adjusted p below 0.05, reversed when it has the opposite sign with such a p, and not confirmed otherwise.

| Comparison | Expected on the test split | Validation (Holm p over attainable outcomes) |
|---|---|---|
| C vs A (fine-tuning, single role) | C accepts more | p = 1.2e-16 |
| D vs B (fine-tuning, multi-role) | D accepts more | p from 1.7e-13 to 1.5e-11 |
| D vs C (coordination, adapted role) | C accepts more | p = 1.1e-5 |
| B vs A (coordination, original model) | none | p from 0.125 to 0.73 |

The intervals describe the sampling variation of an 84-case validation estimate; the test split comes from unseen families, so a missed target is a finding to report, not a reason to re-tune. Targets are thresholds, not hypothesis tests. The validation run meets all of its own targets by construction (checked in `tests/test_evaluation_freeze.py`).

## Running the test split

1. Commit the frozen state, then build and upload a bundle from the clean tree (the lane refuses a test job from a modified tree), with the adapter above.
2. Run once: `scripts/evaluate.py --split test --provider local --model-config <config naming this model and adapter, ideally with adapter_config_sha256> --arms A,B,C,D --i-confirm-frozen-test --protocol-version eval-v1` (through the Kaggle lane's test job).
3. Report every attempt: `scripts/report_evaluation.py <records.jsonl> --out <directory> --targets experiments/evaluation/protocol-freeze.json`.

## Qualitative assessment

Shahd reviews a sample of proposals from every arm (all failures if there are few) with the fixed task rubric, records ambiguous cases and failure patterns (for example wrong negation, lost exit, changed exception, unparseable output, review loops), and keeps the notes next to the evaluation records. Model-generated content is never treated as ground truth.

## Release acceptance

The agreed P0 behavior must run on the demonstration machine and from a clean clone in a fresh environment. Prefer a second physical machine; if unavailable, label the reproduction as same-laptop clean setup and record cross-machine validation as untested. The release needs reproducible results, an error analysis, documented limitations and a supervisor review. A working prototype does not depend on proving that the research hypothesis is true.
