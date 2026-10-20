# Evaluation protocol eval-v1 (draft)

Status: **draft, not frozen** (2026-10-20, data and evaluation workstream, coding agent working for Shahd Abdelhay; pending the owner's review and the P2 supervisor discussion). The executable part is `src/refactor_ai/evaluation/protocol.py`. The protocol becomes frozen only when `experiments/evaluation/protocol-freeze.json` is written with `"status": "frozen"` after the validation baseline and before any test-split run (see "Freezing"). Any change to arms, budgets, generation settings, measures or data after the freeze requires a new protocol version (eval-v2) and is reported as exploratory.

## Questions and comparisons

The comparison separates the effect of fine-tuning from the effect of role coordination on one task (`guard_clauses`, task version 1, prompt `refactor-v1`).

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
- Before timing, the harness runs the runner's self-checks and one untimed warm-up generation per adapter state (recorded in the run manifest). The arm order rotates from case to case so no arm always runs first.
- One attempt per (case, arm). A run interrupted by infrastructure may be resumed (`--resume`) for missing attempts only; completed attempts are never repeated to obtain a better outcome.

## Data

- Baseline, prompt checks and adapter selection: the validation split (84 cases from 12 unseen families).
- Final comparison: the frozen test split, 88 cases (12 unseen template families plus 3 MBPP and 1 HumanEval functions), split hash `b765dbb8ba3c3f76771ed6aa4a05e645372de19751f720805ccfc511d5535b72` ([freeze record](../../experiments/data/test-split-freeze.json)). The four real-source cases are also reported separately; pretraining overlap with these public benchmarks cannot be excluded.
- The harness refuses the test split unless `--i-confirm-frozen-test` and `--protocol-version eval-v1` are given, the protocol is frozen, the provider is the local model and the split hash matches the freeze record.

## Measures and denominators

N is the number of attempted cases of an arm. Every rate uses N as its denominator, so failures, timeouts and harness exceptions count as non-success; nothing missing is counted as zero. A measurement that could not be taken is null with a reason in the record.

| Measure | Definition |
|---|---|
| Overall acceptance (primary) | Disposition `proposal_ready`: syntax and rubric pass, reference tests pass, and the review accepts (B, D) or is not run (A, C) |
| Syntax validity | The final proposal parses (`ast.parse`) |
| Rubric success | `guard_clauses.rubric` passes (structure only, not behavior) |
| Reference-test pass | All reference tests pass; also reported over the cases whose tests executed |
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
- `null_reasons` and `warnings`.

A run manifest (`run.json`) stores the command, arms and settings, dataset identity, case ids, provider and runner information, warm-up results and the test-split authorization evidence. Tables and figures are produced only from the records: `python -m uv run python scripts/report_evaluation.py <records.jsonl> --out experiments/evaluation/<evaluation-id>` (summary.md, CSV tables, report.json and SVG figures).

## Freezing and numerical targets

1. Run the validation baseline (arms A and B with the original model; C and D once an adapter has been selected on validation data only) and report it with the same tables.
2. Then, and before any test-split run, write `experiments/evaluation/protocol-freeze.json` with: `protocol_version` (eval-v1), `status` "frozen", the freeze date, the model revision, the adapter id and SHA-256, the generation settings above, the harness code SHA, the dataset and test-split hashes, and the numerical targets.
3. Targets are set from the validation baseline, for example a minimum syntax validity and a minimum overall acceptance for the delivered configuration, and are fixed before the test split is seen. They are not set in this draft.
4. Run the test split once with `--i-confirm-frozen-test --protocol-version eval-v1` and report every attempt.

## Qualitative assessment

Shahd reviews a sample of proposals from every arm (all failures if there are few) with the fixed task rubric, records ambiguous cases and failure patterns (for example wrong negation, lost exit, changed exception, unparseable output), and keeps the notes next to the evaluation records. Model-generated content is never treated as ground truth.

## Release acceptance

The agreed P0 behavior must run on the demonstration machine and from a clean clone in a fresh environment. Prefer a second physical machine; if unavailable, label the reproduction as same-laptop clean setup and record cross-machine validation as untested. The release needs reproducible results, an error analysis, documented limitations and a supervisor review. A working prototype does not depend on proving that the research hypothesis is true.
