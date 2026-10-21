# Evaluation protocol eval-v1 (draft)

Status: **draft, not frozen** (2026-10-20, data and evaluation workstream, coding agent working for Shahd Abdelhay; pending the owner's review and the P2 supervisor discussion). The executable part is `src/refactor_ai/evaluation/protocol.py`. The protocol becomes frozen only when `experiments/evaluation/protocol-freeze.json` is written with `"status": "frozen"` after the validation baseline and before any test-split run (see "Freezing"). Any change to arms, budgets, generation settings, measures or data after the freeze requires a new protocol version (eval-v2) and is reported as exploratory.

## Questions and comparisons

The comparison separates the effect of fine-tuning from the effect of role coordination on one task (`guard_clauses`, task version 1, prompt `refactor-v2`: the fenced code first, then one `Explanation:` line; selected on validation records only).

| Arm | Model configuration | Workflow | WorkflowSettings |
|---|---|---|---|
| A | Original model | Refactoring role only | `mode=single_role`, `refactor_use_adapter=false`, `max_calls=1`, `max_corrections=0` |
| B | Original model | Analysis, refactoring and review, at most one correction | `mode=multi_role`, `refactor_use_adapter=false`, `max_calls=5`, `max_corrections=1` |
| C | LoRA adapter on the refactoring role | Refactoring role only | `mode=single_role`, `refactor_use_adapter=true`, `max_calls=1`, `max_corrections=0` |
| D | LoRA adapter on the refactoring role; analysis and review on the original model | Analysis, refactoring and review, at most one correction | `mode=multi_role`, `refactor_use_adapter=true`, `max_calls=5`, `max_corrections=1` |

Pre-declared paired comparisons on the same cases: B vs A (coordination, original model), C vs A (fine-tuning, single role), D vs C (coordination, adapted role) and D vs B (fine-tuning, multi-role).

## Fixed settings (identical for every arm)

- One loaded base model at one pinned revision; arms C and D use one adapter identified by id and SHA-256 (recorded per call in `ModelReference`).
- Generation: greedy decoding (`temperature=0`, `top_p=1`), `seed=42`, `max_input_tokens=2048`, `timeout_s=120` per call; `max_new_tokens` 384 for analysis, 768 for refactoring and 384 for review.
- Run timeout 600 s per case; budgets as in the table. The harness counts every provider call itself and flags any call beyond `max_calls` or any adapter flag that does not match the arm.
- The trusted reference runner from the verification workstream (`refactor_ai.verification.create_runner("auto")`) runs each case's reference tests; when its isolation checks fail, tests are `not_run` and never count as a pass.
- Before timing, the harness runs the runner's self-checks and one untimed warm-up generation per adapter state (recorded in the run manifest). When an attempt ends with the model worker stopped (a generation timeout or a worker crash), the untimed warm-up runs again before the next attempt, so the model reload is not charged to another case; each re-warm-up is listed in the manifest summary (`rewarm`). The arm order rotates from case to case so no arm always runs first.
- One attempt per (case, arm). A run interrupted by infrastructure may be resumed for missing attempts only, with `--resume --evaluation-id <id>` (the id is printed when the run starts; `--resume` without the id, or for an id without records, is refused). Completed attempts are never repeated to obtain a better outcome. If an interrupted write left an unterminated last line in `records.jsonl`, the resumed run moves those bytes to `records.jsonl.partial-at-byte-<offset>` (kept, not deleted), lists the move in the manifest summary (`repaired_last_line`), and attempts that case again because its record was never written.

## Data

- Baseline, prompt checks and adapter selection: the validation split (84 cases from 12 unseen families).
- Final comparison: the frozen test split, 88 cases (12 unseen template families plus 3 MBPP and 1 HumanEval functions), case-content hash `3a1e6b95ce74dbd1acdd76207eefcead31eeb255cc3b24a1e6d3955f90e75d12` and refactor-v2 rendered hash `27b6d0ece9430ee30a96617949a31e1c71a0a5c0be7187b36bc660d998e95633` ([freeze record](../../experiments/data/test-split-freeze.json)). The four real-source cases are also reported separately; pretraining overlap with these public benchmarks cannot be excluded.
- The harness refuses the test split unless `--i-confirm-frozen-test` and `--protocol-version eval-v1` are given, the protocol is frozen, the provider is the local model, and both the rendered split hash and the case-content hash match the freeze record. The single test run covers every test case, so `--limit`, `--case-ids` and `--runner disabled` are refused. After the warm-up and before the first attempt, the run also stops if the reference runner is not enabled (for example when its isolation self-checks fail), if a warm-up call failed (for example a missing adapter), or if a warm-up call reports a model identity other than the `model` object of the protocol freeze record (adapter fields are compared for adapter calls).

## Measures and denominators

N is the number of attempted cases of an arm. Every rate uses N as its denominator, so failures, timeouts and harness exceptions count as non-success; nothing missing is counted as zero. A measurement that could not be taken is null with a reason in the record. A failed run has no final proposal, so its syntax, rubric and reference-test outcomes are `not_run` and never count as a success, even when the workflow had checked its last proposal before the failure (for example when the review call timed out in arm B or D).

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

Paired comparisons count, over cases attempted by both arms, how many cases each arm accepts that the other does not, with the two-sided exact McNemar p-value and a Holm adjustment over the four comparisons. Rates come with their counts. Cases come from 16 source groups, so cases are not independent; results are reported by family as well, and conclusions are limited to this task, these cases and this model. Passing reference tests supports behavior preservation only on the tested inputs. Exception messages are not compared by the tests.

## Case-level record

`scripts/evaluate.py` writes one JSON line per (case, arm) to `runs/evaluation/<evaluation-id>/records.jsonl`, validated by `refactor_ai.evaluation.records.EvaluationRecord`:

- identity: `evaluation_id`, `protocol_version`, `protocol_status`, `arm`, `order_position`, `case_id`, `split`, `source`, `source_group`, `dataset_sha256`, `split_sha256`, `code_sha`, `started_at`, `evaluator`;
- model: `provider_mode`, `model`, `models_used` (every distinct model identity reported per call), `settings` (full WorkflowSettings), `generation_seed`;
- input and output: `input_sha256`, `output_sha256`, `proposed_code`, `explanation`, and per call the role, adapter flag, model, elapsed time, token counts, finish reason, error code and raw output (`calls`);
- outcome: `run_status`, `disposition`, `disposition_reasons`, `stop_reason`, `error`, `failure_type`, `syntax`, `rubric`, `rubric_failed_checks`, `reference_tests` (status and counts), `model_review`, `recheck`, `proposal_ready`;
- cost: `attempt_count`, `reported_call_count`, `call_count`, `calls_by_role`, `prompt_tokens`, `completion_tokens`, `latency_s`, `stage_timings`, `worker_peak_rss_mb`, `gpu_memory_used_mb`;
- `null_reasons` and `warnings` (for a failed run whose workflow had checked its last proposal, a `failed_run_checks:` warning keeps those statuses for error analysis).

Each record is one LF-terminated line; U+0085, U+2028 and U+2029 inside strings are written as JSON escapes, and readers split on LF only. A run manifest stores the command, arms and settings, dataset identity, case ids, provider and runner information, warm-up results, the test-split authorization evidence and the run summary. It is written after the warm-up (so an interrupted segment keeps one) and again when the segment ends. The first segment writes `run.json`; each resumed segment writes its own `run-<UTC time>.json` and lists the earlier manifests, so no segment's manifest is overwritten. Tables and figures are produced only from the records: `python -m uv run python scripts/report_evaluation.py <records.jsonl> --out experiments/evaluation/<evaluation-id>` (summary.md, CSV tables, report.json and SVG figures).

## Freezing and numerical targets

1. Run the validation baseline (arms A and B with the original model; C and D once an adapter has been selected on validation data only) and report it with the same tables.
2. Then, and before any test-split run, write `experiments/evaluation/protocol-freeze.json` with: `protocol_version` (eval-v1), `status` "frozen", the freeze date, the model identity as a `model` object with the `ModelReference` fields `model_id`, `model_revision`, `adapter_id` and `adapter_sha256` (the test run compares the warm-up's reported identity with it), the generation settings above, the harness code SHA, the dataset and test-split hashes, and the numerical targets.
3. Targets are set from the validation baseline, for example a minimum syntax validity and a minimum overall acceptance for the delivered configuration, and are fixed before the test split is seen. They are not set in this draft.
4. Run the test split once with `--i-confirm-frozen-test --protocol-version eval-v1` and report every attempt.

## Qualitative assessment

Shahd reviews a sample of proposals from every arm (all failures if there are few) with the fixed task rubric, records ambiguous cases and failure patterns (for example wrong negation, lost exit, changed exception, unparseable output), and keeps the notes next to the evaluation records. Model-generated content is never treated as ground truth.

## Release acceptance

The agreed P0 behavior must run on the demonstration machine and from a clean clone in a fresh environment. Prefer a second physical machine; if unavailable, label the reproduction as same-laptop clean setup and record cross-machine validation as untested. The release needs reproducible results, an error analysis, documented limitations and a supervisor review. A working prototype does not depend on proving that the research hypothesis is true.
