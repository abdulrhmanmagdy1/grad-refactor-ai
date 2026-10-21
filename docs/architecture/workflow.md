# Workflow coordinator and verification

This page describes what `refactor_ai.agents.coordinator.run_workflow` actually does. It implements the [component contracts](contracts.md) for the [guard_clauses task](../requirements/task-scope.md); where the contract left a choice open, the interpretation is stated here. Code: [src/refactor_ai/agents/](../../src/refactor_ai/agents/) and [src/refactor_ai/verification/](../../src/refactor_ai/verification/). Tests: `tests/test_agents_*.py`, `tests/test_verification_*.py` and `tests/test_runner*.py`.

```python
run_workflow(request: WorkflowRequest, *, provider, settings: WorkflowSettings,
             runner: ReferenceRunner | None = None,
             on_status: StatusCallback | None = None) -> WorkflowOutcome
run_workflow_traced(...) -> tuple[WorkflowOutcome, WorkflowTrace]
```

`run_workflow` never raises for run errors: every failure becomes a well-formed outcome. `run_workflow_traced` returns the same outcome plus a `WorkflowTrace` with one `CallRecord` per provider call (role, attempt, prompt version, requested adapter flag, timeout, reported model identity, elapsed time, tokens, finish reason, raw output and parse outcome) and the emitted statuses. Schema version 1 has no field for per-call identities or for the analysis and review raw outputs, so evaluation scripts should use the traced variant.

## Sequence

1. **Validate** (no model call). Multi-role settings with `max_calls < 3` fail as `invalid_settings`. A `reference_case` whose task type differs or whose `original_code` differs from the submitted code (after newline normalization and ignoring trailing whitespace, the API's rule) fails as `reference_case_mismatch`. Then `guard_clauses.check_input`: unsupported input completes as `no_change`. If `check_input` raises `RecursionError` (valid code within the size limits whose expression nesting is deeper than the recursive `ast` helpers of the reference rewrite allow, for example a `return` of several hundred terms joined by `+`), the rewrite cannot lower the nesting depth, so the run completes as `no_change` with `no_opportunity` and a warning instead of failing as `internal_error`.
2. **Analyze** (multi-role only): one call with prompt `analysis-v1`. The output is parsed strictly; findings are validated one by one. When the result is unusable (unparseable after the one repair, `supported_task: false`, or no valid finding), the deterministic opportunities from `check_input` are used with `source=static` and a warning. Validation decides the scope; the analysis model cannot turn a supported input into `no_change`.
3. **Generate**: one refactoring call with the shared refactoring prompt from `task_format` (version `task_format.PROMPT_VERSION`, currently `refactor-v2`: the code block first, then one `Explanation:` line); multi-role runs add the findings as analysis notes, single-role runs never do. The output is parsed with `task_format.parse_refactor_output` (at most one deterministic repair).
4. **Verify**: syntax with `ast.parse` only, the task rubric, and the trusted reference tests through the runner, each recorded separately. Nothing is executed in the calling process.
5. **Review** (multi-role only): one call with prompt `review-v1`, which shows the original under `Code:`, the deterministic results and the proposal.
6. **Correct once** (multi-role only): when no code was produced, a deterministic check failed (syntax, rubric, reference tests `fail` or `error`) or the review rejected, one corrected generation with prompt `correction-v2` follows, then its verification and one more review. A review that is `uncertain` or unparseable, and tests that are `not_available` or `not_run`, do not trigger a correction.

The correction is started only when `max_corrections >= 1` and at least two calls remain (the corrected generation and its review). The final proposal is the corrected one; if the correction produced no parseable code, the first proposal and its verification are reported with a warning. There is never a second correction.

The correction prompt holds the code twice (the original and the previous answer), so it is the one prompt that can exceed the refactoring role's `max_input_tokens` when the first prompt fit. The coordinator has no tokenizer, so it does not guess: the provider counts the rendered prompt exactly and refuses it with `input_too_long` before generating. A refusal of the **corrected generation** skips the correction: the run completes with stop reason `correction_input_too_long`, a warning that quotes the provider's token count, and the first proposal with its full verification (the refused call is counted in `call_count` and recorded as attempt 1 without code). `input_too_long` anywhere else (analysis, first generation, either review) fails the run like any provider error. See [token budgets](#token-budgets).

## Budgets and time

| Mode | Calls | Order |
|---|---|---|
| single-role (arms A, C) | exactly 1 | refactor |
| multi-role (arms B, D) | at most `max_calls` (5) | analysis, refactor, review, refactor (correction), review |

The refactoring calls request `use_adapter = settings.refactor_use_adapter`; analysis and review always request the base model. If a provider reports a different `use_adapter` than requested, the run fails with `model_load_error`: a silent adapter fallback would invalidate the comparison.

Each call uses its role's `GenerationConfig` from `settings.generation`; the defaults are analysis 384 new tokens, 2,048 input tokens, 60 s; refactoring 1,024, 2,048, 120 s; review 768, 4,096, 90 s. `settings.run_timeout_s` bounds the whole run: the time left is checked before every model call and before every verification step, and each call's `timeout_s` is the smaller of the role's timeout and the time left. When the time is used up, the run fails with `run_timeout` at the step that could not start; a provider timeout on a call whose timeout was shortened to the time left is also reported as `run_timeout`. The runner receives the time left as its wall-clock limit when it supports it.

## Status transitions

Reported through `on_status`; the coordinator never reports `queued` (the API sets it).

| Path | Statuses |
|---|---|
| Multi-role | analyzing, generating, verifying, completed |
| Multi-role with correction (also when the correction prompt is refused as too long) | analyzing, generating, verifying, generating, verifying, completed |
| Single-role | generating, verifying, completed |
| Unsupported input | completed |
| Invalid settings or reference case | failed |
| Failure in a step | the statuses so far, then failed |

The model review runs while the status is `verifying`. Every generation is followed by `verifying`, also when its output could not be parsed or the provider refused the correction prompt as too long, so the only backward transition is the single `verifying -> generating` of the correction. A status callback that raises is logged and recorded as a warning; the run continues.

## Stop reasons

| `stop_reason` | Status | Meaning |
|---|---|---|
| `unsupported_input` | completed | Validation rejected the input; zero calls; disposition `no_change` |
| `single_role_complete` | completed | The single generation was verified |
| `no_correction_needed` | completed | Multi-role: nothing failed and the review did not reject |
| `correction_used` | completed | Multi-role: the one correction was generated and verified |
| `correction_disabled` | completed | A correction was needed but `max_corrections` is 0 |
| `call_budget_exhausted` | completed | A correction was needed but fewer than two calls were left |
| `correction_input_too_long` | completed | The provider refused the correction prompt as too long; the first proposal is reported |
| `provider_error` | failed | A provider call failed; `error.code` is the `ProviderErrorCode` |
| `run_timeout` | failed | `run_timeout_s` was used up |
| `unparseable_output` | failed | No attempt produced parseable code |
| `invalid_settings` | failed | Multi-role with `max_calls < 3` |
| `reference_case_mismatch` | failed | The reference case does not match the code |
| `internal_error` | failed | An unexpected exception; details are logged, not shown |

`error.code` is one of `timeout`, `model_load_error`, `input_too_long`, `generation_error`, `busy`, `unavailable` (from the provider), `run_timeout`, `unparseable_output`, `invalid_settings`, `reference_case_mismatch` or `internal_error`. `error.stage` is `validation`, `analysis`, `generation`, `verification` or `review`. Provider messages are reduced to their first line; a message that starts with a traceback is replaced, and unexpected exceptions never reach the message. When the correction was needed but not possible and the first answer had no code, the run fails as `unparseable_output` and the warnings say why no correction was made.

## Verification and disposition

`VerificationResult` keeps four dimensions separate:

| Dimension | Values | Notes |
|---|---|---|
| `syntax` | pass, fail, not_run | `ast.parse` only; `not_run` when there is no code |
| `rubric` | pass, fail, not_run | `not_run` when the proposal does not parse |
| `reference_tests` | pass, fail, error, not_available, not_run | see below |
| `model_review` | accept, reject, uncertain, error, not_run | `error` when the review output cannot be parsed |

Reference tests are `not_available` when no reference case was selected or the case has no tests; `not_run` when no runner is configured, the runner is disabled, the proposal does not parse, or the proposal leaves the task constraints (imports, dunder access, denied calls, nested definitions, more than one function). Such proposals are never handed to the runner. A proposal that only fails other rubric checks (for example nesting not reduced) is still tested, because the result is informative.

The disposition follows the contract's order: `failed` and `no_change` are decided by the coordinator; then `rejected` if syntax fails, the rubric fails, tests fail or error, or the review rejects; then `uncertain` if the review is uncertain or errored, a multi-role review did not run, tests are `not_available` or `not_run`, or a deterministic check did not run; otherwise `proposal_ready`. A `pass` counts only with at least one test and every test passed. A model accept never overrides a failed deterministic check, and passing tests is never presented as proof for every input.

Every entry of `disposition_reasons` is `<code>: <sentence>`. The codes are the task's reason codes for `no_change` (for example `too_long`, `denied_call:print`), the error code for `failed`, and `syntax_fail`, `rubric_fail`, `tests_fail`, `tests_error`, `review_reject`, `review_uncertain`, `review_error`, `review_not_run`, `tests_not_available`, `tests_not_run`, `check_not_run` or `ready` otherwise. Split at the first `": "` to separate the code from the sentence.

## Outcome fields

| Field | Completed run | Failed run |
|---|---|---|
| `proposed_code`, `explanation` | final attempt (also for `rejected` and `uncertain`) | `None` |
| `diff`, `changed_lines` | computed by the application with `difflib` from the original and the proposal (never from model output) | `None`, `[]` |
| `verification` | final attempt's result | disposition `failed`; deterministic results of the attempt under review if the review step failed |
| `analysis`, `findings` | report used for the notes (multi-role); static report with `supported_task: false` for `no_change`; `None` and `[]` for single-role | as far as reached |
| `review` | final attempt's parsed review (multi-role) | `None` |
| `attempts` | one `AttemptRecord` per refactoring call, including a call that failed | same |
| `model` | model identity of the final proposal's refactoring call | identity of the last call |
| `warnings` | repairs, dropped findings, fallbacks, token limits, fake-provider label | same |

`diff` is a unified diff from `original.py` to `proposed.py` after line endings are normalized; it is empty when the code is unchanged. `changed_lines` lists 1-based line numbers of the proposal that were inserted or replaced; lines that were only removed appear in the diff. The submitted code is never modified.

## Parsing

The refactoring output uses `task_format.parse_refactor_output` unchanged (errors `empty_output`, `no_code_block`, `unterminated_code_block`; repairs `unfenced_code`, `multiple_code_blocks`). The analysis and review outputs are parsed strictly, then repaired at most once: remove a code fence that surrounds the whole output (it opens on the first line and its closing fence ends the output or is missing; a code block next to the JSON or a ```` ``` ```` inside a JSON string is left alone), extract the first balanced `{...}` object that is valid JSON (or, when none is, the first balanced object, whose JSON error is reported), and (review only) normalize the verdict's case. Unknown keys, wrong types (no string-to-number or string-to-boolean coercion) and more than ten review reasons are errors; `schema_version` and `source` written by a model are ignored. Analysis findings are validated individually: a finding with another type than `nested_conditional`, lines outside the input, an end before its start, or invalid fields is dropped with a warning; at most 20 are kept. The model is never called again to fix its output.

## Prompts

| Version | Role | Content |
|---|---|---|
| `analysis-v1` | analysis | JSON shape of `AnalysisReport`, then the code under `Code:` |
| `refactor-v2` | refactor | `task_format` prompt (`prompts.REFACTOR_PROMPT_VERSION` is `task_format.PROMPT_VERSION`); multi-role adds `Analysis notes:` |
| `correction-v2` | refactor | the unchanged `refactor-v2` prompt, then the previous answer and the concrete problems; it asks for "the required format" and never restates it, so the only format description is the embedded code-first one |
| `review-v1` | review | the deterministic results, the JSON shape of `ReviewResult`, the original under `Code:` and the proposal |

In every prompt the first `Code:` block holds the submitted code and comes before any model-written text, so `extract_submitted_code` (used by `FakeProvider`) always finds the original. The correction feedback lists syntax errors, rubric reasons, reference-test counts and up to three failure details (call, expected and actual values), and the reviewer's reasons and suggestion. Showing failing test cases to the model is oracle feedback that only multi-role runs receive; the evaluation must report it. Changing any prompt requires a new prompt version and a new protocol version. `prompts.CORRECTION_EMBEDS` names the refactoring version the correction embeds, and a test fails when `task_format.PROMPT_VERSION` moves on without a new correction version.

## Token budgets

Measured on 2026-10-20 with the pinned Qwen2.5-Coder-0.5B-Instruct tokenizer (loaded on the CPU from `models/`, no model weights), counting the chat template with the assistant turn opened exactly as the model worker does. Limits are the default `max_input_tokens`.

| Input | Code chars / tokens | Analysis (2,048) | Refactor multi-role (2,048) | Review (4,096) | Correction (2,048) |
|---|---|---|---|---|---|
| Largest train and validation records (842 chars) | 842 / 184 | 384 | 440 | 600 | 723 |
| Demonstration cases (355 to 802 chars) | up to 190 tokens | 390 | 486 | 610 | 773 |
| Synthetic 2,945-char function, long names | 2,945 / 627 | 827 | 809 | 1,489 | 1,538 |
| Synthetic 2,999-char function, 46 lines | 2,999 / 544 | 744 | 764 | 1,321 | 1,408 |
| Synthetic 2,981-char function, string building | 2,981 / 792 | 992 | 1,012 | 1,817 | 1,904 |
| Synthetic 60-line function, short arithmetic | 2,537 / 1,034 | 1,234 | 1,254 | 2,301 | **2,388** |
| Digit-dense 2,935-char function | 2,935 / 1,999 | **2,199** | **2,181** | (5,105) | (7,250) |

The synthetic and digit-dense inputs are constructed to probe the limits; they are not dataset records, and the frozen test split was not read. Reading the table:

- **Review.** Realistic inputs leave at least 1,795 tokens spare. The worst case that can reach the review is bounded by the earlier prompts: the largest digit-dense original whose analysis prompt still fits (2,028 tokens) plus a candidate at the refactoring role's 1,024 output tokens plus maximal digit-filled check lines measured 3,965 tokens (131 spare); with realistic check lines the same case measured 3,093. A review prompt that still exceeds 4,096 (possible only with adversarial content, for example check lines full of multi-token characters) fails the run cleanly with `input_too_long` at stage `review`.
- **Correction.** It is about twice the code tokens plus 300, so it fits up to roughly 870 code tokens: realistic code up to the 3,000-character limit fits, but dense code (short names and digits, about 2.5 characters per token) above roughly 2,100 characters does not. Those runs complete as `correction_input_too_long`.
- **Digit-dense input.** Qwen tokenizes digits one by one (about 1.5 characters per token), so a 3,000-character function full of numbers exceeds 2,048 already in the analysis and first refactoring prompts; such runs fail cleanly with `input_too_long` before any review or correction (the bracketed numbers are never sent).

## Known limits

- The fake provider's outputs are fixtures; every outcome produced with it carries a warning saying so.
- Code containing a Markdown fence (```) makes the fenced blocks in every prompt ambiguous; the run continues with a warning.
- The analysis and review raw outputs and the per-call model identities exist only in `WorkflowTrace` until the contract adds a field for them.
- The runner is a hardening layer for trusted demonstration cases, not a sandbox for hostile code; see [runner safety](../development/runner-safety.md).
