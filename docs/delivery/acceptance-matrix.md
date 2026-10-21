# Acceptance matrix (T23)

Status: working draft of 2026-10-21, prepared by the coding agent for the agent workflow and verification workstream (T23 owner Abdullah Tarek) and pending his inspection. It traces every requirement of the [software requirements](../requirements/srs.md) to code, automated tests and retained records. It was first written at commit `3ffb16f` and refreshed after commit `74daf25`, once the training record, the validation baseline, the protocol freeze, the single test-split evaluation, the report and the clean-clone reproduction were committed. It is not a release claim: the slides, the release and every human review are still open. The checklist walk-through is in [acceptance status](acceptance-status.md).

## How to read this matrix

| Status | Meaning |
|---|---|
| Implemented and tested | The behavior exists and automated tests exercise the acceptance criterion; the tests passed in the snapshot below or in the recorded run named in the row |
| Implemented, evidence pending | The behavior exists and its mechanics are tested, but the evidence the criterion asks for (for example real-model output or an experiment record) does not exist yet |
| Partially implemented | Part of the criterion is met; the missing part is named |
| Not implemented | Nothing implements the criterion |
| Excluded | Deliberately outside the first release |

Evidence rules applied:

- Tests that use the deterministic fake provider (`FakeProvider`, `ScriptedWorkflow` or scripted provider stubs) show the plumbing only. They count as evidence for deterministic behavior (validation, budgets, verification, records, API), never for model behavior.
- Real-model evidence comes only from records under `experiments/` produced with Qwen/Qwen2.5-Coder-0.5B-Instruct at revision `ea3f2471cf1b1f0db85067f1ef93848e38e88c25`. Git-ignored files under `runs/` are working output, not committed evidence.
- Supervisor approval is not implied anywhere: no supervisor review has been held (see [supervisor reviews](../supervisor-reviews/README.md)).

## Test snapshot used for this matrix

Python tests were collected and run on 2026-10-21 (from 09:17 UTC) on the demonstration laptop, Windows 11, Python 3.11.9, at commit `ee87a11` on `main` with uncommitted changes of the active workstreams in the working tree (backend, workflow, runner, evaluation and test files). The suite was run file group by file group through the shared lock, not as one invocation, because of the laptop's memory limit.

```
python -m uv run pytest --collect-only -q -p no:cacheprovider <files>   # 1,501 items in 27 files
python -m uv run pytest -q -p no:cacheprovider <files>
```

| Batch | Files | Result |
|---|---|---|
| 1 | `test_guard_clauses.py`, `test_task_format.py`, `test_agents_parsing.py`, `test_agents_prompts.py`, `test_fake_provider.py`, `test_contract_examples.py` | 210 passed |
| 2 | `test_agents_coordinator.py`, `test_verification_checks.py`, `test_verification_registry.py` | 633 passed |
| 3 | `test_api.py`, `test_api_runs.py`, `test_api_app.py` | 127 passed, 1 warning |
| 4 | `test_runs_components.py`, `test_runs_config.py`, `test_runs_records.py`, `test_runs_service.py`, `test_runs_store.py` | 144 passed |
| 5 | `test_evaluation_harness.py`, `test_evaluation_report.py`, `test_dataset.py`, `test_local_provider.py`, `test_local_provider_gpu.py` | 106 passed, 8 skipped |
| 6 | `test_runner_child.py`, `test_runner.py` (real processes, Windows path) | 235 passed |
| 7 | `test_data_executor.py`, `test_data_curation.py`, `test_data_committed.py` | 38 passed |
| Total | 27 files | 1,493 passed, 8 skipped, 0 failed |

- The 8 skipped tests are `tests/test_local_provider_gpu.py`, which needs `REFACTOR_AI_GPU_TESTS=1` and the GPU. They were not run here (the GPU is busy with training); their last recorded run passed 8 of 8 on 2026-10-20 with the pilot adapter ([record](../../experiments/models/2026-10-20-local-provider-gpu-tests.json)).
- Frontend tests were not re-run for this matrix, because the interface workstream is changing `frontend/` at the time of writing. The last recorded result is 488 passed and 5 skipped (the optional end-to-end file) in 13 files on 2026-10-21 for the interface of commit `ee87a11` ([frontend notes](../report/notes/frontend.md)). Frontend test names below are quoted from that commit.
- GitHub Actions results were not queried for the first version of this matrix.

**Refresh at `74daf25`.** A clean clone from GitHub on the same laptop passed every check: 1,551 Python tests passed and 8 were skipped (the GPU file), and the interface passed 491 tests with 5 skipped ([clean-clone record](../../experiments/qa/2026-10-21-clean-clone-reproduction.md)). GitHub Actions passed on Ubuntu, Windows and the frontend job for every push to `main` from `d2d2f0b` to `74daf25` ([CI record](../../experiments/qa/2026-10-21-clean-worktree-verification.md#github-actions)). The eight GPU provider tests passed again on 2026-10-21 with the trained adapter served in bfloat16 on the laptop ([record](../../experiments/models/2026-10-20-local-provider-gpu-tests.json)). Interface test names quoted below come from `ee87a11`; some changed with the interface redesign of `bad4095`, while the test files are the same.

## Summary

| ID | Requirement | Priority | Status | Justification |
|---|---|---|---|---|
| FR01 | Accept bounded Python input | P0 | Implemented and tested | The 20,000-character limit, blank, malformed and invalid-syntax rejections and the zero-call `no_change` path are deterministic and tested for every exclusion reason; no model is involved. |
| FR02 | Analyze code | P0 | Implemented and tested | The static rules and the coordinator's finding checks (type `nested_conditional`, lines inside the input, static fallback) hold for any model output; the quality of model-written findings is unmeasured. |
| FR03 | Propose a refactoring | P0 | Implemented and tested | Every result shape is tested with fake and scripted providers, and the committed validation and test-split records show the real model producing proposals through the coordinator in all four arms; one service run with the fine-tuned model is recorded. |
| FR04 | Verify a proposal | P0 | Implemented and tested | Four separate dimensions and the disposition order (all 450 combinations) are tested, also with the real runner; missing tests are `not_available` or `not_run` and never a pass. |
| FR05 | Show a diff | P0 | Implemented and tested | The application computes the diff and changed lines itself (a model-supplied diff is ignored), and the interface shows unified and side-by-side views with the analysed lines. |
| FR06 | Preserve user control | P0 | Implemented and tested | Accept, reject and download are explicit; the original input is kept verbatim and the service writes nothing to host files. |
| FR07 | Trace each run | P0 | Implemented and tested | `RunRecord` stores the id, settings, model identity, status, timings, attempts and errors; the real worker's identity reporting passed in the recorded GPU tests. |
| FR08 | Bound execution | P0 | Implemented and tested | Call, correction, token, per-call and per-run limits are tested; the real worker's token and timeout enforcement passed in the recorded GPU tests. |
| FR09 | Compare experiments | P0 | Implemented and tested | Harness, arms, test-split guard and report are tested; the protocol was frozen from the validation baseline and arms A to D ran once on the same 88 test cases, with case-level records, tables and figures committed. |
| FR10 | Retain run history | P1 | Implemented and tested | SQLite history with list, get, delete, retention and restart recovery is tested and was checked manually on the laptop. |
| NFR01 | The API never executes code | Quality | Implemented and tested | Input is parsed with `ast` only; file-writing snippets submitted to both endpoints never create their file. |
| NFR02 | Limited separate runner | Quality | Partially implemented | Time, CPU, memory and process limits are enforced by the operating system, but network and file-system limits only by an in-process audit hook, and there is no privilege boundary when the service runs as a normal user. |
| NFR03 | No paid API or committed credentials | Quality | Implemented and tested | Fake mode is the default and the local model runs offline without an account; a pattern scan found no credentials in tracked files. |
| NFR04 | Python 3.11, lockfile, separate GPU stack | Quality | Implemented and tested | `pyproject.toml` pins Python 3.11, CI and the foundation check use `uv sync --frozen`, and the GPU stack is pinned separately. |
| NFR05 | Experiment records identify their inputs | Quality | Partially implemented | The test-split evaluation was run from a clean committed tree and its records identify code, data, model, adapter, settings and hardware; the training record and the validation baseline name their commit but were produced from working trees with uncommitted changes. |
| NFR06 | Tests are not proof of equivalence | Quality | Implemented and tested | The ready reason, the interface and the report say that passing tests cover the tested inputs only; the slides do not exist yet. |
| NFR07 | Response-time and memory targets | Quality | Partially implemented | Load time, decode speed and memory were measured on the laptop, but no targets have been declared. |

Counts over the 17 requirements: 14 implemented and tested, none with evidence pending, 3 partially implemented (NFR02, NFR05, NFR07), none not implemented, none excluded. (At `3ffb16f`: 12 implemented and tested, 3 with evidence pending, 2 partially implemented.) Delivery items that are not requirements (training record, final evaluation, clean-clone reproduction, report, slides, release) are tracked in [acceptance status](acceptance-status.md).

## Functional requirements

### FR01 Accept bounded Python input

Criterion: accept non-blank text up to 20,000 characters; reject larger or malformed requests understandably; input outside the [task scope](../requirements/task-scope.md) completes as `no_change` with reason codes and no model call.

- Implementation: `RunCreateRequest` and `MAX_CODE_CHARS` in [contracts.py](../../src/refactor_ai/contracts.py); request handling and error mapping in [api.py](../../src/refactor_ai/api.py) and [runs/errors.py](../../src/refactor_ai/runs/errors.py); scope rules in `check_input` of [tasks/guard_clauses.py](../../src/refactor_ai/tasks/guard_clauses.py); the zero-call path in [agents/coordinator.py](../../src/refactor_ai/agents/coordinator.py).
- Tests: [tests/test_api_runs.py](../../tests/test_api_runs.py) `test_input_limit_is_20000_characters`, `test_invalid_requests_are_validation_errors`, `test_malformed_bodies_are_validation_errors`, `test_undecodable_bodies_are_validation_errors`, `test_blank_code_error_matches_the_published_example`, `test_invalid_syntax_reports_the_location`, `test_unparseable_code_is_invalid_syntax`; [tests/test_api_app.py](../../tests/test_api_app.py) `test_oversized_bodies_are_rejected_before_parsing`; [tests/test_api.py](../../tests/test_api.py) `test_invalid_syntax_and_empty_input`, `test_parser_limits_are_reported_as_invalid_syntax`; [tests/test_guard_clauses.py](../../tests/test_guard_clauses.py) `test_out_of_scope_inputs_are_rejected_with_reason` (12 cases), `test_too_long_input`, `test_flat_function_has_no_opportunity`; [tests/test_agents_coordinator.py](../../tests/test_agents_coordinator.py) `test_unsupported_input_completes_without_calls` (7 reasons in both modes, zero calls), `test_unsupported_task_type_is_no_change`, `test_expression_too_deep_for_the_rewrite_completes_as_no_change`.
- Interface: `frontend/src/App.test.tsx` "enables Propose refactoring only for non-blank code within the API limit", "warns above the task limit but still allows submission", "shows invalid_syntax with its line and marks that line", "shows validation errors from the service".
- Other evidence: [error examples](../architecture/examples/README.md) (`error_validation_error.json`, `error_invalid_syntax.json`, `error_payload_too_large.json`, `run_record_no_change.json`); screenshots [s08-no-change-light.png](../report/screenshots/s08-no-change-light.png) and [s09-invalid-syntax-light.png](../report/screenshots/s09-invalid-syntax-light.png) (fake mode).
- Open: the 3,000-character and 60-line task limits are marked preliminary in the task scope and await the P1 supervisor review.

### FR02 Analyze code

Criterion: structured findings with locations and reasons, or an empty result; the foundation rules cover long functions (also async) and nested control blocks; the workflow's analysis reports `nested_conditional` findings whose line ranges lie inside the input.

- Implementation: foundation rules `long-function` and `deep-nesting` in [analysis.py](../../src/refactor_ai/analysis.py) behind POST /api/v1/analyze; static findings from `check_input` in [tasks/guard_clauses.py](../../src/refactor_ai/tasks/guard_clauses.py); the analysis prompt `analysis-v1` in [agents/prompts.py](../../src/refactor_ai/agents/prompts.py); strict parsing with one repair, type and line-range checks in [agents/parsing.py](../../src/refactor_ai/agents/parsing.py) (`ALLOWED_FINDING_TYPES` holds only `nested_conditional`); static fallback with `source=static` in the coordinator.
- Tests: [tests/test_api.py](../../tests/test_api.py) `test_long_async_function`, `test_nesting_is_structural_not_indentation`, `test_analyze_example_matches_the_endpoint`, `test_analysis_does_not_execute_code`; [tests/test_guard_clauses.py](../../tests/test_guard_clauses.py) `test_opportunities_have_valid_lines`; [tests/test_agents_parsing.py](../../tests/test_agents_parsing.py) `test_strict_analysis_is_accepted_without_repair`, `test_invalid_findings_are_dropped_individually`, `test_line_limit_is_inclusive`, `test_findings_are_limited_to_twenty`, `test_one_deterministic_repair`, `test_invalid_analysis_reports_an_error`; [tests/test_agents_coordinator.py](../../tests/test_agents_coordinator.py) `test_findings_outside_the_input_are_dropped_with_warnings`, `test_unusable_analysis_falls_back_to_static_findings`, `test_all_findings_invalid_falls_back_to_static`, `test_fenced_analysis_json_is_repaired`, `test_multi_role_passes_analysis_findings_as_notes`.
- Other evidence: [analysis_report.json](../architecture/examples/analysis_report.json), [analyze_response.json](../architecture/examples/analyze_response.json).
- Open: the analysis role ran with the real model in arms B and D of the validation and test-split evaluations, but the evaluation report does not summarize how often the model's findings were usable rather than replaced by the static fallback. The criterion itself holds regardless, because the coordinator enforces it.

### FR03 Propose a refactoring

Criterion: proposed code, an explanation and the refactoring type `guard_clauses`, or an explicit `no_change` or failure with a reason.

- Implementation: the refactor-v2 prompt and parser in [task_format.py](../../src/refactor_ai/task_format.py); generation, correction and failure mapping in [agents/coordinator.py](../../src/refactor_ai/agents/coordinator.py); the real model in `providers/local.py` and `providers/model_worker.py` (models workstream); the fake stand-in in [providers/fake.py](../../src/refactor_ai/providers/fake.py).
- Tests (fake or scripted providers): [tests/test_agents_coordinator.py](../../tests/test_agents_coordinator.py) `test_single_role_happy_path`, `test_multi_role_happy_path`, `test_single_role_unparseable_output_fails`, `test_multi_role_fails_when_both_answers_are_unparseable`, `test_provider_error_codes_are_mapped` (6 codes), `test_provider_timeout_in_each_role_fails_the_run`, `test_provider_tracebacks_are_not_shown_to_users`, `test_unexpected_exception_becomes_internal_error`; [tests/test_task_format.py](../../tests/test_task_format.py) `test_refactor_v2_puts_the_code_block_first`, `test_completion_renders_and_parses`, `test_parse_errors_are_typed`, `test_parse_repairs_are_marked`; [tests/test_contract_examples.py](../../tests/test_contract_examples.py) `test_run_record_examples_cover_the_states`, `test_coordinator_records_use_documented_stop_reasons_and_reason_codes`.
- Real-model evidence so far: the validation-only [prompt-format selection](../../experiments/models/2026-10-20-prompt-format-selection.md) ran the base model through `LocalProvider`, the same parser and the same checks on 24 validation records: refactor-v2 parsed 24 of 24, passed the rubric on 5 and was fully acceptable on 2 (14 outputs were unchanged copies of the input). The [pilot reload check](../../experiments/training/pilot-2026-10-20-reload-check.json) covers pilot prompts only. Neither ran the coordinator or the service.
- Real-model evidence through the workflow: the [validation baseline](../../experiments/evaluation/validation-2026-10-21/provenance.json) and the [test-split evaluation](../../experiments/evaluation/test-2026-10-21/targets-report/summary.md) ran all four arms through the coordinator. On the 88 test cases every arm produced a parseable proposal in at least 87 cases, and the fine-tuned single-role arm C reached `proposal_ready` in 70; arm A failed once with `unparseable_output`. The service itself ran the fine-tuned model on a demonstration case and ended `proposal_ready` with 6 of 6 reference tests passed ([integration record](../../experiments/integration/2026-10-21-first-real-model-run.json)); the interface screenshots in [docs/report/screenshots/](../report/screenshots/) were taken with that model.

### FR04 Verify a proposal

Criterion: syntax, task rubric, trusted reference tests and the agent's review presented as separate results; missing tests never count as a pass.

- Implementation: [verification/checks.py](../../src/refactor_ai/verification/checks.py), [verification/disposition.py](../../src/refactor_ai/verification/disposition.py), the rubric in [tasks/guard_clauses.py](../../src/refactor_ai/tasks/guard_clauses.py), the runner in [verification/runner.py](../../src/refactor_ai/verification/runner.py) and [runner_child.py](../../src/refactor_ai/verification/runner_child.py), review parsing in [agents/parsing.py](../../src/refactor_ai/agents/parsing.py); `VerificationResult` in [contracts.py](../../src/refactor_ai/contracts.py); `frontend/src/components/VerificationPanel.tsx`.
- Tests: [tests/test_verification_checks.py](../../tests/test_verification_checks.py) `test_disposition_order` (450 combinations), `test_pass_without_complete_counts_is_not_a_pass`, `test_no_case_is_not_available`, `test_case_without_tests_is_not_available`, `test_missing_runner_is_not_run`, `test_model_accept_never_overrides_a_failed_check`, `test_rejected_lists_every_failure`, `test_rubric_failure_alone_still_runs_tests`, `test_runner_exception_becomes_error`, `test_runner_returning_garbage_becomes_error`, `test_syntax_pass_and_fail`, `test_rubric_pass_fail_and_not_run`; [tests/test_agents_coordinator.py](../../tests/test_agents_coordinator.py) `test_reference_test_status_drives_disposition`, `test_missing_reference_case_is_not_available_and_uncertain`, `test_missing_runner_is_not_run_and_uncertain`, `test_model_accept_never_overrides_failed_tests`, `test_malformed_review_is_an_error_and_uncertain`, `test_rubric_failure_is_rejected_and_reported`, `test_real_runner_proposal_ready`, `test_real_runner_failure_drives_the_correction`; [tests/test_runner.py](../../tests/test_runner.py) `test_correct_candidate_passes`, `test_wrong_value`, `test_wrong_exception`, `test_missing_exception`, `test_unexpected_exception`, `test_comparison_semantics`, `test_shipped_cases_through_the_workflow`; [tests/test_guard_clauses.py](../../tests/test_guard_clauses.py) `test_rubric_reports_each_failure`; [tests/test_api_runs.py](../../tests/test_api_runs.py) `test_reference_case_run_passes_the_trusted_case`, `test_default_wiring_runs_a_real_demo_case_end_to_end`.
- Interface: `frontend/src/components/results.test.tsx` "shows four separate cards and the equivalence note", "never draws missing reference tests or review like a pass", "explains a missing review in single-role runs", "marks a fake provider's accept as a placeholder without the pass tone"; `frontend/src/test/contractExamples.test.tsx` renders every run-record example.
- Other evidence: [workflow](../architecture/workflow.md) and [contracts](../architecture/contracts.md) define the order; the six demonstration cases' original and reference code pass all 52 tests in the runner (`test_shipped_cases_pass_with_their_original_and_reference_code`); screenshots [s05b-diff-and-verification-light.png](../report/screenshots/s05b-diff-and-verification-light.png) and [s07b-uncertain-verification-light.png](../report/screenshots/s07b-uncertain-verification-light.png) (fake mode).
- Open: the review dimension is shown separately. With the real model the review role is unreliable: in the validation run 87 of 260 base-model review outputs reached the 384-token limit while repeating themselves and became review `error`, which leaves an otherwise passing proposal `uncertain`; 34 of arm D's 88 test cases ended `uncertain` ([protocol](../evaluation/protocol.md), [test results](../../experiments/evaluation/test-2026-10-21/targets-report/summary.md)).

### FR05 Show a diff

Criterion: display added and removed lines and the affected components.

- Implementation: [verification/diffing.py](../../src/refactor_ai/verification/diffing.py) computes the unified diff and `changed_lines` from the two texts; `RunRecord.diff`, `changed_lines` and `findings` (line ranges and reasons of the affected conditionals) in [contracts.py](../../src/refactor_ai/contracts.py); `frontend/src/components/DiffViewer.tsx` and `frontend/src/lib/diff.ts` (unified and side-by-side views).
- Tests: [tests/test_verification_checks.py](../../tests/test_verification_checks.py) `test_unified_diff_and_changed_lines`, `test_inserted_lines_are_reported_in_proposal_numbering`, `test_identical_code_has_no_diff`, `test_line_endings_are_normalized`; [tests/test_agents_coordinator.py](../../tests/test_agents_coordinator.py) `test_model_supplied_diff_is_ignored`; the shared invariant check in that file recomputes the diff after every workflow test.
- Interface: `frontend/src/components/results.test.tsx` "renders the unified diff with line numbers and change markers", "switches to the side-by-side view of the full texts", "falls back to the raw text when the diff cannot be parsed"; `frontend/src/lib/diff.test.ts` (22 tests per the frontend notes).
- Other evidence: screenshots [s05b-diff-and-verification-light.png](../report/screenshots/s05b-diff-and-verification-light.png) and [s06-side-by-side-light.png](../report/screenshots/s06-side-by-side-light.png) (fake mode).

### FR06 Preserve user control

Criterion: acceptance, rejection and download without automatically modifying the original input.

- Implementation: GET /api/v1/runs/{run_id}/proposal and POST /api/v1/runs/{run_id}/decision in [api.py](../../src/refactor_ai/api.py); proposal rules in [runs/records.py](../../src/refactor_ai/runs/records.py); `frontend/src/components/DecisionPanel.tsx` and `ProposalActions.tsx`.
- Tests: [tests/test_api_runs.py](../../tests/test_api_runs.py) `test_decisions_are_recorded_and_can_change`, `test_decision_before_the_run_finishes_is_refused`, `test_any_completed_proposal_can_be_downloaded_and_decided`, `test_proposal_download_is_a_safe_attachment`, `test_proposal_unavailable_until_finished_and_without_code`, `test_failed_run_has_no_proposal`, `test_line_endings_are_normalized_before_storage`; [tests/test_agents_coordinator.py](../../tests/test_agents_coordinator.py) `test_original_code_is_kept_verbatim`; [tests/test_runs_records.py](../../tests/test_runs_records.py) `test_apply_outcome_keeps_identity_and_input`, `test_proposal_rules`.
- Interface: `frontend/src/App.test.tsx` "records accept and reject without touching the input", "downloads the proposal through the service", "hides copy, download and the decision when there is no proposal", "shows them for a proposal that verification did not approve, with a warning".
- Other evidence: the end-to-end file `frontend/src/test/e2e.test.ts` passed once against the real service in fake mode (frontend notes); screenshot [s12-decision-recorded-light.png](../report/screenshots/s12-decision-recorded-light.png).

### FR07 Trace each run

Criterion: record an identifier, configuration, model version, state, duration and failures.

- Implementation: `RunRecord`, `WorkflowSettings`, `ModelReference`, `StageTiming`, `AttemptRecord` and `RunError` in [contracts.py](../../src/refactor_ai/contracts.py); [runs/service.py](../../src/refactor_ai/runs/service.py) and [runs/store.py](../../src/refactor_ai/runs/store.py); `run_workflow_traced` in the coordinator; `frontend/src/components/RunDetails.tsx`.
- Tests: [tests/test_runs_service.py](../../tests/test_runs_service.py) `test_run_completes_with_outcome_and_timestamps`, `test_non_terminal_statuses_are_persisted_as_they_happen`, `test_failed_outcome_keeps_the_workflow_error`, `test_settings_runner_and_reference_case_reach_the_workflow`; [tests/test_runs_records.py](../../tests/test_runs_records.py) `test_outcome_mapping_covers_every_workflow_outcome_field`; [tests/test_agents_coordinator.py](../../tests/test_agents_coordinator.py) `test_failed_generation_call_is_recorded_as_an_attempt`, `test_run_workflow_returns_the_traced_outcome`, `test_adapter_is_requested_for_the_refactoring_role_only`; [tests/test_local_provider.py](../../tests/test_local_provider.py) `test_success_reports_identity_tokens_and_mode`, `test_adapter_identity_and_per_call_switch`.
- Real-model evidence: `test_greedy_call_reports_identity_and_is_repeatable` and `test_adapter_switch_and_disabled_adapter_equals_base` passed on the GPU on 2026-10-20 ([record](../../experiments/models/2026-10-20-local-provider-gpu-tests.json)).
- Other evidence: run-record examples in [examples/](../architecture/examples/README.md); screenshot [s05c-run-record-light.png](../report/screenshots/s05c-run-record-light.png).

### FR08 Bound execution

Criterion: limits on calls, retries, generated tokens and elapsed time: one call in single-role runs, at most five calls and one correction in multi-role runs, per-role token and time limits and a whole-run time limit.

- Implementation: `WorkflowSettings` and `GenerationConfig` in [contracts.py](../../src/refactor_ai/contracts.py); budget, correction and deadline logic in [agents/coordinator.py](../../src/refactor_ai/agents/coordinator.py); token and timeout enforcement in the model worker (`providers/local.py`, `providers/model_worker.py`).
- Tests: [tests/test_agents_coordinator.py](../../tests/test_agents_coordinator.py) `test_single_role_runs_with_one_call_budget`, `test_single_role_never_corrects_even_when_rejected`, `test_correction_exhaustion_stops_after_five_calls`, `test_correction_needs_two_remaining_calls`, `test_multi_role_needs_three_calls`, `test_correction_disabled`, `test_generation_settings_are_applied_per_role`, `test_run_deadline_caps_the_call_timeout`, `test_run_deadline_is_checked_before_the_next_call`, `test_run_deadline_is_checked_before_verification`, `test_call_timeouts_never_exceed_the_remaining_run_time`, `test_token_limit_finish_is_warned`, `test_oversized_correction_prompt_skips_the_correction`; [tests/test_local_provider.py](../../tests/test_local_provider.py) `test_max_new_tokens_reports_length`, `test_timeout_kills_only_the_worker_and_next_call_restarts`, `test_input_too_long_keeps_the_worker`, `test_load_timeout_kills_the_loading_worker`; [tests/test_evaluation_harness.py](../../tests/test_evaluation_harness.py) `test_budget_and_adapter_violations_become_warnings`.
- Real-model evidence: `test_max_new_tokens_is_enforced`, `test_timeout_kills_the_gpu_worker_and_the_next_call_restarts` and `test_input_too_long_is_typed_and_keeps_the_worker` passed on the GPU on 2026-10-20 ([record](../../experiments/models/2026-10-20-local-provider-gpu-tests.json)); token budgets were measured with the pinned tokenizer ([workflow token budgets](../architecture/workflow.md#token-budgets)).
- Note: the frozen evaluation protocol uses other per-role limits than the service defaults; the report states that the A/B/C/D results describe the protocol's limits (see [inconsistencies](#inconsistencies-found-while-tracing)).

### FR09 Compare experiments

Criterion: evaluate the agreed variants on the same test cases and export results.

- Implementation: arms A to D and fixed settings in [evaluation/protocol.py](../../src/refactor_ai/evaluation/protocol.py); [evaluation/harness.py](../../src/refactor_ai/evaluation/harness.py), [records.py](../../src/refactor_ai/evaluation/records.py), [report.py](../../src/refactor_ai/evaluation/report.py), [resources.py](../../src/refactor_ai/evaluation/resources.py); [scripts/evaluate.py](../../scripts/evaluate.py) and [scripts/report_evaluation.py](../../scripts/report_evaluation.py); protocol text in [evaluation protocol](../evaluation/protocol.md).
- Tests (stub workflow and fake provider): [tests/test_evaluation_harness.py](../../tests/test_evaluation_harness.py) `test_arms_follow_the_contract_and_share_generation_settings`, `test_run_evaluation_writes_every_attempt_and_resumes`, `test_failures_are_recorded_with_types`, `test_test_split_guard`, `test_a_test_split_run_stops_before_any_attempt_unless_it_is_complete_and_ready`, `test_test_readiness_needs_the_frozen_model_identity`, `test_metered_provider_forwards_and_counts`, `test_recheck_detects_disagreement_with_the_workflow`, `test_warm_up_runs_once_per_adapter_state`; [tests/test_evaluation_report.py](../../tests/test_evaluation_report.py) `test_build_report_writes_tables_and_valid_svg`, `test_denominators_include_failures`, `test_exact_mcnemar_and_holm`, `test_checks_of_a_failed_run_never_count_as_successes`, `test_fake_provider_reports_are_labelled`; [tests/test_data_committed.py](../../tests/test_data_committed.py) `test_test_split_is_frozen`, `test_frozen_test_case_content_never_changes`.
- Other evidence: [harness plumbing check](../../experiments/evaluation/2026-10-20-harness-plumbing-check.json) (fake provider, 6 validation cases, 24 attempts; explicitly not a model result); [test-split freeze record](../../experiments/data/test-split-freeze.json).
- Model comparison: the [validation baseline](../../experiments/evaluation/validation-2026-10-21/provenance.json) of arms A to D, the [protocol freeze record](../../experiments/evaluation/protocol-freeze.json) with twelve numerical targets and expected directions, and the single [test-split run](../../experiments/evaluation/test-2026-10-21/targets-report/summary.md) under protocol eval-v1 (88 cases per arm; accepted A 7, B 1, C 70, D 35; 11 of 12 targets met, D's acceptance floor missed). The run was pushed from the clean commit `9582c66` ([provenance](../../experiments/evaluation/test-2026-10-21/provenance.json)).

### FR10 Retain run history (P1)

Criterion: retrieve previous results on the demonstration machine.

- Implementation: [runs/store.py](../../src/refactor_ai/runs/store.py) (SQLite, write-ahead log, exclusive lock file), GET /api/v1/runs and DELETE /api/v1/runs/{run_id} in [api.py](../../src/refactor_ai/api.py), retention in [runs/service.py](../../src/refactor_ai/runs/service.py); `frontend/src/components/HistoryPanel.tsx`.
- Tests: [tests/test_runs_store.py](../../tests/test_runs_store.py) `test_history_survives_reopening`, `test_list_is_newest_first_with_insertion_order_for_equal_times`, `test_retention_prunes_oldest_finished_runs_only`, `test_recover_unfinished_marks_only_non_terminal_runs`, `test_a_second_store_on_the_same_file_is_refused`, `test_delete`; [tests/test_api_runs.py](../../tests/test_api_runs.py) `test_run_list_is_newest_first_and_bounded`, `test_retention_keeps_the_newest_runs`, `test_delete_removes_the_record`, `test_deleting_a_waiting_run_skips_it`; [tests/test_api_app.py](../../tests/test_api_app.py) `test_restart_applies_a_lower_retention`.
- Interface: `frontend/src/App.test.tsx` "lists runs newest first with status and disposition chips", "deletes a run only after confirmation", "reopens a failed run with its error and retries the same input".
- Other evidence: manual restart check on the laptop, 2026-10-20 ([backend notes](../report/notes/backend.md#evidence)); screenshot [s13-history-delete-light.png](../report/screenshots/s13-history-delete-light.png).

## Quality requirements

### NFR01 The API does not execute submitted or generated code

- Implementation: `ast.parse` only in [analysis.py](../../src/refactor_ai/analysis.py), [api.py](../../src/refactor_ai/api.py) and [verification/checks.py](../../src/refactor_ai/verification/checks.py); proposals run only in the separate runner process (NFR02).
- Tests: [tests/test_api.py](../../tests/test_api.py) `test_analysis_does_not_execute_code`, `test_parser_limits_are_reported_as_invalid_syntax`; [tests/test_api_runs.py](../../tests/test_api_runs.py) `test_runs_never_execute_submitted_or_generated_code`, `test_real_coordinator_with_fake_provider_does_not_execute_code`; [tests/test_agents_coordinator.py](../../tests/test_agents_coordinator.py) `test_candidate_outside_task_constraints_is_never_executed`; [tests/test_runner.py](../../tests/test_runner.py) `test_syntax_error_is_reported_without_starting_a_process`.
- Status: implemented and tested. Submitted code is never executed anywhere; generated proposals for the six server-owned demonstration cases are executed only by the runner process, as NFR02 allows.

### NFR02 Separate runner with CPU, memory, time, network, file-system and privilege limits

- Implementation: [verification/runner.py](../../src/refactor_ai/verification/runner.py), [runner_child.py](../../src/refactor_ai/verification/runner_child.py), [policy.py](../../src/refactor_ai/verification/policy.py), [_winjob.py](../../src/refactor_ai/verification/_winjob.py); described in [runner safety](../development/runner-safety.md).
- Tests: [tests/test_runner.py](../../tests/test_runner.py) `test_self_checks_enable_execution`, `test_failed_self_checks_disable_execution`, `test_disabled_runner_never_executes`, `test_infinite_loop_hits_the_wall_clock_limit`, `test_cpu_bound_loop_hits_the_cpu_limit`, `test_memory_bomb_is_stopped_by_the_memory_limit`, `test_operating_system_blocks_child_processes_without_the_hook`, `test_audit_hook_blocks_network`, `test_audit_hook_blocks_file_writes_and_host_reads`, `test_audit_hook_blocks_processes_and_native_code`, `test_environment_is_scrubbed_and_workdirs_removed`, `test_introspection_is_blocked_even_when_the_policy_admits_the_code`, `test_result_channel_cannot_be_forged`, `test_policy_refuses_candidates_before_execution`, `test_privilege_drop_only_under_root`; [tests/test_runner_child.py](../../tests/test_runner_child.py) `test_import_policy`, `test_file_access_policy`, `test_blocked_in_every_phase`, `test_blocked_once_candidate_code_runs`, `test_removed_builtins_are_the_denied_ones`.
- Other evidence: all 19 isolation self-checks passed on the laptop ([runner safety](../development/runner-safety.md#isolation-checklist), [plumbing record](../../experiments/evaluation/2026-10-20-harness-plumbing-check.json)) and as root on Kaggle in the validation and test runs; the Linux path as a normal user passed in the Ubuntu CI job of every push from `a546f84` on ([CI record](../../experiments/qa/2026-10-21-clean-worktree-verification.md#github-actions)).
- Status: partially implemented. Met by the operating system: wall clock, CPU time, memory, one process, cleanup, empty environment and a temporary working directory (Windows Job Object; Linux resource limits). Met only by the audit hook inside the candidate's own interpreter: network and file-system limits (Linux also sets `RLIMIT_FSIZE` to 0). Privilege: the test process runs as the service's user on Windows and on Linux unless the service runs as root, in which case it drops to user 65534. The runner safety page states that this is not a security boundary for hostile code and lists a restricted token, AppContainer or namespaces as future work.

### NFR03 No paid API or committed credentials for basic operation

- Implementation: fake provider by default ([config.py](../../src/refactor_ai/config.py)); the local worker runs with `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`; `.gitignore` excludes `.env`, `.env.*`, `configs/*.local.json`, `models/`, `runs/` and `data/`; `.env.example` holds no values.
- Tests: [tests/test_runs_config.py](../../tests/test_runs_config.py) `test_documented_defaults`; [tests/test_runs_components.py](../../tests/test_runs_components.py) `test_fake_provider_by_default`; [tests/test_local_provider.py](../../tests/test_local_provider.py) `test_example_config_is_valid_and_pinned`.
- Other evidence: on 2026-10-21 `git grep` over tracked files for Hugging Face, Kaggle, GitHub and OpenAI-style token patterns returned no match (a pattern scan, not a proof). The Kaggle lane, used for training only, authenticates with a token outside the repository (`~/.kaggle/access_token`, [Kaggle lane](../../training/kaggle/README.md)).

### NFR04 Python 3.11 with a lockfile; GPU dependencies resolved separately

- Implementation: `requires-python = ">=3.11,<3.12"` in [pyproject.toml](../../pyproject.toml), `.python-version`, [uv.lock](../../uv.lock); GPU stack pinned in [training/requirements-cuda.txt](../../training/requirements-cuda.txt) (PyTorch 2.14.1+cu126 on the laptop).
- Tests and checks: `.github/workflows/ci.yml` runs `uv sync --frozen` on Ubuntu and Windows; [tests/test_local_provider.py](../../tests/test_local_provider.py) `test_core_imports_do_not_load_torch` keeps the GPU stack out of the core environment; foundation check `uv sync --frozen: pass` in the [hardware record](../../experiments/hardware/2026-10-20-demonstration-laptop.json); [training environment record](../../experiments/hardware/2026-10-20-training-environment.json).
- Note: the Kaggle lane keeps Kaggle's own PyTorch (2.11.0+cu128 on Python 3.13 in its smoke job) and pins only the Hugging Face packages, as the [Kaggle lane](../../training/kaggle/README.md) describes. Any result produced there must name that environment, not the laptop's.

### NFR05 Experiment records identify code, data, model revision, configuration, seed and hardware

- Implementation: [experiments/run-template.json](../../experiments/run-template.json); evaluation record and manifest fields in [evaluation/records.py](../../src/refactor_ai/evaluation/records.py) and [harness.py](../../src/refactor_ai/evaluation/harness.py); training run manifests written by `training/train_lora.py` (models workstream).
- Tests: [tests/test_evaluation_harness.py](../../tests/test_evaluation_harness.py) `test_completed_record_has_every_measurement`, `test_each_run_segment_keeps_its_own_manifest`, `test_tokens_are_null_with_reason_when_the_provider_does_not_report_them`; [tests/test_data_committed.py](../../tests/test_data_committed.py) `test_manifest_matches_the_records`.
- Records with these fields: [pilot training record](../../experiments/training/pilot-2026-10-20.json), [failed full-run record](../../experiments/training/full-2026-10-20-local-attempt1-failed.json), [benchmark run 2](../../experiments/models/2026-10-20-qwen2.5-coder-0.5b-instruct-benchmark-run2.json), the [training record](../../experiments/training/full-2026-10-21.json) of the adopted adapter, the [validation provenance](../../experiments/evaluation/validation-2026-10-21/provenance.json) and the [test-split provenance](../../experiments/evaluation/test-2026-10-21/provenance.json); the [curation run](../../experiments/data/curation-run.json) records command, seed, commit and platform for the data (no model is involved).
- Status: partially implemented. The test-split evaluation was built from the clean commit `9582c66` (`git_dirty: false`, 91 bundled files verified in the kernel), so its code is recoverable exactly. The training record names commit `a546f84` with `working_tree_dirty: true` and the validation baseline names `ee87a11` with `git_dirty: true`, so their exact code cannot be recovered from the commit alone; for the validation baseline a replay without a model checks which later code changes could affect its outcomes ([code-change check](../../experiments/evaluation/validation-2026-10-21/code-change-check.json)).

### NFR06 Passing tests are not presented as proof of equivalence

- Implementation: the ready reason in [verification/disposition.py](../../src/refactor_ai/verification/disposition.py); the note in `frontend/src/components/VerificationPanel.tsx`; wording in the [task scope](../requirements/task-scope.md), [user guide](user-guide.md) and [evaluation protocol](../evaluation/protocol.md).
- Tests: [tests/test_verification_checks.py](../../tests/test_verification_checks.py) `test_ready_reason_states_the_limits_of_testing`; `frontend/src/components/results.test.tsx` "shows four separate cards and the equivalence note".
- Other evidence: the [data plan](../data-and-training/data-plan.md#reference-tests-curation-only-executor) documents concrete gaps in the reference tests (untested branch, undetected non-equivalent mutants, float rounding).
- Open: the [report](../report/report.md) keeps the wording; the slides do not exist yet and must keep it too.

### NFR07 Response-time and memory targets set after measurement

- Measurements: model load 17.6 s warm and 88.1 s cold, decode 13.8 to 26.1 tokens per second, model process about 1.0 GB of GPU memory ([benchmark records](../../experiments/models/README.md)); runner self-checks about 5 to 10 s and about 0.3 s per test process ([runner safety](../development/runner-safety.md)); training memory against sequence length ([training records](../../experiments/training/README.md)).
- Status: partially implemented. Measurements exist, but no document declares response-time or memory targets yet. The test-split evaluation recorded latency and memory per case on a Kaggle T4 (median latency 3.0 s for arm A, 7.7 s for C, 16.0 s for B and 17.9 s for D; worker peak 2,259 MB of RAM and 2,615 MB of GPU memory; [test results](../../experiments/evaluation/test-2026-10-21/targets-report/summary.md)), which gives a basis for targets; on the laptop in bfloat16 the adapter roughly halves decoding speed ([laptop adapter check](../../experiments/models/2026-10-21-laptop-adapter-check.json)).

## Use cases

| Use case | Evidence | State |
|---|---|---|
| UC01 Submit a valid example, inspect the change, download an accepted result | `test_submit_poll_and_fetch`, `test_proposal_download_is_a_safe_attachment` ([tests/test_api_runs.py](../../tests/test_api_runs.py)); `frontend/src/test/e2e.test.ts` run once against the real service in fake mode; a service run with the fine-tuned model ([integration record](../../experiments/integration/2026-10-21-first-real-model-run.json)) and the screenshots taken with it | Tested; shown with the real model on demonstration cases |
| UC02 Submit invalid Python and receive an error without executing it | `test_invalid_syntax_reports_the_location`, `test_runs_never_execute_submitted_or_generated_code` | Tested |
| UC03 See a clear reason for a generation or verification failure | `test_provider_error_codes_are_mapped`, `test_workflow_exception_is_a_failed_run_without_internals`, `test_rejected_lists_every_failure`; `frontend/src/App.test.tsx` "reopens a failed run with its error and retries the same input" | Tested with fake and scripted failures |
| UC04 Run a comparison experiment and export case-level records and a summary | [tests/test_evaluation_harness.py](../../tests/test_evaluation_harness.py), [tests/test_evaluation_report.py](../../tests/test_evaluation_report.py), [plumbing record](../../experiments/evaluation/2026-10-20-harness-plumbing-check.json), [test-split evaluation](../../experiments/evaluation/test-2026-10-21/targets-report/summary.md) | Done with the model on Kaggle (validation and test split) |

## Deferred and excluded scope

No requirement of the specification is excluded. The following are outside the first release by the [task scope](../requirements/task-scope.md#outside-the-three-week-release) and the [runner safety](../development/runner-safety.md#honest-limits) page, and must be reported as such:

| Item | Kind |
|---|---|
| Refactoring types other than `guard_clauses`; several functions, classes, methods, files, repositories and other languages | Excluded |
| Async functions, generators, decorators, `try`/`with`/`match`, imports, nested definitions | Excluded (inputs complete as `no_change`) |
| Rewriting conditionals inside loops; NaN-aware inverted comparisons; preserving comments and formatting in the reference transformation | Excluded |
| Executing user-supplied tests or code; model-generated tests as evidence; automatic changes to user files; claims of equivalence for all inputs | Excluded |
| Operating-system network, file-system and privilege boundary for the runner (restricted token, AppContainer, namespaces, container) | Deferred (future work; see NFR02) |
| Response-time and memory targets | Deferred (see NFR07) |

## Inconsistencies found while tracing

These were found while building the matrix at `3ffb16f` and routed to the owning workstreams. The state after `74daf25` follows each item.

1. **Generation limits differ between the service and the evaluation protocol.** The service defaults in `WorkflowSettings` ([contracts.py](../../src/refactor_ai/contracts.py), also stated in the [task scope](../requirements/task-scope.md#limits-and-budgets)) are 1,024 new tokens for refactoring, 768 new tokens and 4,096 input tokens for review, and per-call time limits of 60, 120 and 90 s. The draft protocol ([protocol.py](../../src/refactor_ai/evaluation/protocol.py), [protocol](../evaluation/protocol.md#fixed-settings-identical-for-every-arm)) uses 768 for refactoring, 384 for review, 2,048 input tokens and 120 s for every role. The models workstream notes that 768 new tokens can cut off the longest realistic functions. Before the freeze, the evaluation owner should either align the protocol or state in the report that A/B/C/D results describe the protocol's limits, not the service defaults. *State: reported, not aligned. Protocol eval-v1 was frozen with its own limits, and the report's limitations name the difference and its effect on review outputs ([report](../report/report.md)).*
2. **The model card is out of date**: it names prompt refactor-v1 and says no adapter has been trained on the curated dataset ([model card](../data-and-training/model-card.md)). The models workstream owns the update after the full training record. *State: fixed in `90462d3`.*
3. **The execution state is stale**: [execution-state.json](../agent-execution/execution-state.json) still has `last_verified_commit` `3aa2998`, steps 1 and 2 in progress and steps 3 to 5 not started. *State: fixed in `90462d3`; steps 0 to 4 completed, step 5 pending human review.*
4. **The testing page describes only the foundation tests** and says the tests do not establish runner isolation ([testing](../development/testing.md)), which no longer matches the runner tests. *State: fixed after `74daf25`; the [testing page](../development/testing.md) describes the current suite, CI and the clean-clone record.*
5. **The PDF edition is a planning edition** (0.3, baseline commit `6aea445`, [edition notes](../pdf/README.md)) and does not describe the implementation. *State: open.*
6. **Fresh checkouts do not reproduce two curation outputs** under `curate_dataset.py --check` (line-ending-dependent hashes of the pilot files; [data plan](../data-and-training/data-plan.md#command-and-reproducibility)). This affects the clean-clone reproduction. *State: fixed in `74daf25`; the inventory hashes the content with LF line endings, and `--check` passed on a fresh CRLF clone ([clean-clone record](../../experiments/qa/2026-10-21-clean-clone-reproduction.md)).*
7. **The frontend install was recorded as `npm install` from the pinned manifest**, not `npm ci` ([frontend notes](../report/notes/frontend.md#evidence)); the clean-clone reproduction should run `npm ci` as the setup guide says. *State: done; the clean clone ran `npm ci`, and CI runs it on every push.*
