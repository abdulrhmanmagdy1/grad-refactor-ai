# Component contracts (schema version 1)

Status: agreed implementation contract for the first release (T11). The Pydantic models in [src/refactor_ai/contracts.py](../../src/refactor_ai/contracts.py) are authoritative; this page explains how components use them. Any field change updates the models, this page, the example JSON in [examples/](examples/) and the contract tests together.

## Supported task (task version 1)

One refactoring type is supported: `guard_clauses`, Fowler's "Replace Nested Conditional with Guard Clauses". The single definition lives in [src/refactor_ai/tasks/guard_clauses.py](../../src/refactor_ai/tasks/guard_clauses.py) and is shared by the service, curation, training and evaluation.

- **Input scope.** Exactly one synchronous, undecorated, top-level function; at most 3,000 characters and 60 lines. Excluded: imports, nested functions or classes, global/nonlocal, generators, async, try/with/match blocks, double-underscore names and calls to `open`, `print`, `input`, `exec`, `eval`, `compile`, `__import__`, `globals`, `locals`, `vars`, `setattr`, `delattr`, `breakpoint`, `exit`, `quit`, `help`.
- **Supported case.** Turning conditionals whose branch always returns or raises into guard clauses lowers the maximum control-block nesting depth (an `elif` counts at its `if`'s level). Otherwise the outcome is `no_change` with a reason code.
- **Reference transformation.** `to_guard_clauses()` is a deterministic AST rewrite used to produce curated targets and the fake provider's output. It normalizes formatting through `ast.unparse` (comments are not preserved). It inverts an ordering comparison only when one side is a numeric literal; NaN operands are out of scope.
- **Rubric.** `rubric(original, candidate)` checks: parses as a single function, same name, same signature, same docstring, still inside the task constraints, nesting depth reduced, at least one guard clause, no newly introduced calls. Passing the rubric is not evidence of equal behavior; reference tests are reported separately.

## Refactoring prompt and output format (refactor-v2)

[src/refactor_ai/task_format.py](../../src/refactor_ai/task_format.py) builds the refactoring-role messages and parses its output. Training records store the user message in `prompt` and `render_refactor_completion()` output in `completion`, so the fine-tuned format equals the inference format. The model answers with one fenced Python block followed by an `Explanation: ...` line. Version refactor-v2 replaced the explanation-first refactor-v1 after a validation-only comparison in which the base model stopped before writing code in 22 of 24 records with refactor-v1 and produced code in 24 of 24 with refactor-v2 ([selection record](../../experiments/models/2026-10-20-prompt-format-selection.md)). The parser applies at most one deterministic repair (unfenced code starting at `def`, or multiple blocks) and reports `empty_output`, `no_code_block` or `unterminated_code_block`; it never calls the model again. Every role prompt places the submitted code under a `Code:` line followed by a fenced Python block.

## Model provider

`refactor_ai.providers.base.Provider` exposes `mode`, `info()`, `generate(GenerationRequest) -> GenerationResult` and `close()`. Expected failures are returned in `GenerationResult.error` with a `ProviderErrorCode` (`timeout`, `model_load_error`, `input_too_long`, `generation_error`, `busy`, `unavailable`), never raised. Each result carries the exact `ModelReference` (model id, revision, adapter id and checksum, and whether the adapter was active for that call). A failed adapter load is an error, not a silent fallback to the base model.

- `FakeProvider` (`provider_mode=fake`) is deterministic and test-only. Its explanations and reasons start with `FAKE PROVIDER (not a model):`. Results from it never count as inference, training or evaluation evidence.
- `LocalProvider` (`provider_mode=local_model`, owned by the model workstream) runs the pinned model in a separate worker process launched with the training environment's interpreter, so the core environment and CI never import PyTorch or download weights. A per-call timeout terminates and restarts the worker. One loaded base model serves all roles; `use_adapter` enables the LoRA adapter for a single call.

## Workflow coordinator

`refactor_ai.agents.coordinator.run_workflow(request: WorkflowRequest, *, provider, settings: WorkflowSettings, runner: ReferenceRunner | None = None, on_status: StatusCallback | None = None) -> WorkflowOutcome`

1. **Validate** deterministically with `guard_clauses.check_input`. Unsupported input completes with disposition `no_change`, the reason codes and zero model calls.
2. **Analyze** (multi-role only): one analysis call returning `AnalysisReport` JSON. Findings must reference lines inside the input. If the output cannot be parsed after deterministic repair, the static findings are used with `source=static` and a warning.
3. **Generate**: one refactoring call (multi-role prompts include the findings as analysis notes).
4. **Verify**: syntax, rubric and trusted reference tests, each recorded separately.
5. **Review** (multi-role only): one review call returning `ReviewResult` JSON. The model verdict never overrides a failed deterministic check.
6. **Correct once** (multi-role only): if any check fails or the review rejects, one corrected generation and one more review, then final verification.

Budgets: single-role uses exactly one generation call and no correction. Multi-role uses at most five calls (analysis, generation, review, correction, review). `WorkflowSettings` declares the per-role `GenerationConfig`, `max_calls`, `max_corrections` and `run_timeout_s`. Changing a budget requires a new evaluation protocol version.

Status transitions reported through `on_status`: `queued -> analyzing -> generating -> verifying -> completed | failed`, with at most one `verifying -> generating` transition for the correction. Single-role runs skip `analyzing`.

## Verification and disposition

`VerificationResult` keeps four dimensions separate: `syntax` (pass/fail/not_run), `rubric` (pass/fail/not_run), `reference_tests` (pass/fail/not_available/not_run/error, with counts and a reason) and `model_review` (accept/reject/uncertain/error/not_run). The overall disposition is derived in this order:

1. `failed`: the workflow could not produce a proposal (provider error, timeout, unparseable output, internal error).
2. `no_change`: the input is outside the task scope or has no supported finding.
3. `rejected`: syntax fails, the rubric fails, reference tests fail or error, or the model review rejects.
4. `uncertain`: the model review is uncertain or errored, or reference tests are `not_available` or `not_run`.
5. `proposal_ready`: syntax and rubric pass, reference tests pass, and the review accepts (multi-role) or is `not_run` (single-role).

Missing tests never count as a pass, and passing tests are never presented as proof of equivalence for all inputs.

## Trusted reference runner

`ReferenceRunner.run(case: ReferenceCase, candidate_code: str) -> ReferenceTestsResult` executes only server-owned cases. API callers choose a case by `reference_case_id` from the demonstration allowlist; they cannot submit paths, test code, commands or URLs. The runner executes the candidate in a separate process with a time limit, memory and process limits, no network, an empty environment, a temporary working directory and cleanup. `info()` reports whether isolation self-checks pass; when they do not, execution is disabled and results are `not_run` with the reason.

Each `ReferenceTest` stores `args` and `kwargs` as Python literal source and an expected `return` value (literal source) or `raise` exception type name. Return values are compared by type and equality (floats with `math.isclose`, relative tolerance 1e-9).

Demonstration cases live in `src/refactor_ai/fixtures/demo_cases.json` and are independent of the dataset's test split.

## HTTP API

All endpoints are local. Errors use `ErrorResponse`: `{"error": {"code": ..., "message": ..., "details": [...]}}`.

| Method and path | Result |
|---|---|
| GET /health | `HealthResponse`: actual provider mode and identity, runner status, queue size, and whether the refactoring role uses the adapter |
| POST /api/v1/analyze | Existing static heuristics (unchanged; no model) |
| GET /api/v1/reference-cases | Demonstration allowlist as `ReferenceCaseSummary` items |
| POST /api/v1/runs | 202 `RunAccepted`; 422 `validation_error`, `invalid_syntax`, `unknown_reference_case` or `reference_case_mismatch`; 503 `busy` when the bounded queue is full |
| GET /api/v1/runs | `RunList`, newest first, bounded `limit` (default 20, maximum 50) |
| GET /api/v1/runs/{run_id} | `RunRecord`; 404 `run_not_found` |
| GET /api/v1/runs/{run_id}/proposal | The proposed code as a `.py` attachment; 409 `proposal_unavailable` |
| POST /api/v1/runs/{run_id}/decision | Records the human `accepted` or `rejected` decision; 409 if the run has no proposal |
| DELETE /api/v1/runs/{run_id} | 204; removes the stored record |

A submission with a `reference_case_id` must contain exactly that case's code (line endings normalized), otherwise 422 `reference_case_mismatch`. The service never writes proposals to host files; download happens only after the person inspects the result.

### Project review API

The project review mode ([design](project-review.md)) has its own endpoints. Records are `ProjectRecord` objects ([project/models.py](../../src/refactor_ai/project/models.py)) stored in `projects.sqlite3` next to the run history, with the uploaded files under `projects/<project_id>/`.

| Method and path | Result |
|---|---|
| GET /api/v1/projects/info | Whether reviews use a model (its identity and state), the upload limit and whether the project's tests may run |
| POST /api/v1/projects?name=&run_tests= | The raw request body is the zip (up to 5 MB). 202 with `project_id`, `status` and `poll_url`; 422 `invalid_project` with the intake reason (`empty`, `not_a_zip`, `too_large`, `too_many_files`, `no_python_files`, `unsafe_entry`); 413 `payload_too_large`; 503 `busy` when two reviews are unfinished |
| GET /api/v1/projects | Short records, newest first, bounded `limit` (default 20, maximum 50) |
| GET /api/v1/projects/{project_id} | `ProjectRecord` with status, progress, summary, architecture, findings, fixes, model calls and warnings; 404 `project_not_found` |
| POST /api/v1/projects/{project_id}/fixes/{fix_id}/decision | Records `accepted` or `rejected` for one fix; 404 `fix_not_found`; 409 `fix_unavailable` before the review finished or for a fix without a proposal |
| GET /api/v1/projects/{project_id}/patch | The accepted fixes as one unified diff; 409 `fix_unavailable` when none is accepted |
| GET /api/v1/projects/{project_id}/download | A zip of the project with the accepted fixes applied; 409 as above |
| DELETE /api/v1/projects/{project_id} | 204; removes the record and the uploaded files |

Reviews run on their own worker thread, one at a time. Like runs, a review left unfinished when the service stops becomes `failed` with error code `interrupted` at the next start, and the oldest finished reviews beyond the retention limit are deleted. A request to run the project's tests is ignored, with a warning in the record, unless the service was started with `REFACTOR_AI_PROJECT_TESTS=true`.

Runs are processed by one worker thread through a bounded queue, so model inference is serialized. SQLite stores each `RunRecord` atomically. On startup, stored non-terminal runs become `failed` with error code `interrupted` and are not rerun. Stored runs are capped by a retention limit and can be deleted.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| REFACTOR_AI_PROVIDER | `fake` | `fake` or `local` |
| REFACTOR_AI_MODEL_CONFIG | `configs/model.local.json` | Local model, adapter and worker interpreter settings |
| REFACTOR_AI_DB | `runs/app/runs.sqlite3` | SQLite run history |
| REFACTOR_AI_RUNNER | `auto` | `auto` enables execution only when isolation checks pass; `disabled` forces `not_run` |
| REFACTOR_AI_MAX_PENDING | `4` | Bounded queue size |
| REFACTOR_AI_RETENTION | `200` | Maximum stored runs |
| REFACTOR_AI_REFACTOR_USE_ADAPTER | `false` | `true` runs the refactoring role with the configured LoRA adapter (arms C/D behavior); analysis and review always use the base model |
| REFACTOR_AI_PROJECT_MODEL_CONFIG | `configs/model.project.local.json` | The GGUF model of the project review mode; used with `REFACTOR_AI_PROVIDER=local` when the file exists, otherwise project reviews use the static checks only |
| REFACTOR_AI_PROJECT_TESTS | `false` | `true` lets a project review run the uploaded project's own tests when the person asks for it; off by default because those tests execute the uploaded code on this machine |

The local web interface is served from the same FastAPI process when `frontend/dist` exists. During frontend development, CORS allows only `http://127.0.0.1:5173` and `http://localhost:5173`.

## Implementation details fixed in wave 1

These rules were settled while implementing the components and are covered by their tests.

**Workflow** ([workflow design](workflow.md)):

- Stop reasons for completed runs: `unsupported_input`, `single_role_complete`, `no_correction_needed`, `correction_used`, `correction_disabled`, `call_budget_exhausted`, `correction_input_too_long` (the provider refused the corrected generation as too long; the first proposal is reported with a warning). For failed runs: `provider_error`, `run_timeout`, `unparseable_output`, `invalid_settings`, `reference_case_mismatch`, `internal_error`.
- A correction starts only when two calls remain (the corrected generation and its review). If the correction produces no code, the first proposal is reported with a warning. Unparseable refactoring output in multi-role uses the correction; if no attempt produced code, the run fails with `unparseable_output`.
- A provider that reports a different adapter state than the one requested fails the run with `model_load_error`.
- Multi-role runs with `max_calls` below 3 fail with `invalid_settings`. A multi-role run whose review did not run is `uncertain`, and a reference-test `pass` with zero tests counts as `uncertain`.
- `disposition_reasons` entries have the form `code: sentence`.
- Reference tests run only for proposals that stay inside the task constraints. The runner also refuses aliases of denied builtins (for example `f = eval`) and `getattr` with a computed name.
- The correction prompt shows failing reference tests to the model, so only multi-role arms receive that feedback; the evaluation protocol states this.
- Prompt versions: `refactor-v2`, `analysis-v1`, `review-v1`, `correction-v2` (the correction prompt embeds the refactoring prompt). `run_workflow_traced` also returns a per-call trace (role, prompt version, requested adapter state, reported model identity, raw output and parse outcome) for evaluation.

**Run API** ([backend notes](../report/notes/backend.md)):

- Additional error codes: `service_unavailable` (503 from /health), `payload_too_large` (413, request bodies over 1 MiB), `reference_cases_unavailable` (500, invalid case file), `not_found` (404 for unknown routes), `method_not_allowed` (405 with an `Allow` header), `cors_rejected` (400 for rejected preflight requests) and `internal_error` (500).
- Codes stored on failed runs come from the coordinator (the provider codes plus `run_timeout`, `unparseable_output`, `invalid_settings`, `reference_case_mismatch`, `internal_error`) or from the service: `interrupted`, `workflow_unavailable` and `adapter_unavailable` (the adapter was requested but the provider has none; the run fails before any model call). `RunError.stage` holds a workflow stage, or the run status at the time of an interruption.
- POST /api/v1/runs returns a `Location` header. GET /api/v1/reference-cases returns a plain JSON list. The decision endpoint returns the updated `RunRecord`; the latest decision wins. Any completed run with proposed code can be downloaded or decided, and DELETE works at any status.
- `REFACTOR_AI_MAX_PENDING` counts waiting plus running runs; a full queue returns 503 `busy` with `Retry-After: 10`. Retention removes the oldest finished runs when a run is created and at startup; unfinished runs are never removed.
- Submitted code is stored with LF line endings. A submission matches a reference case when it equals the case's code after normalizing line endings and ignoring trailing whitespace at the end.
- SQLite uses write-ahead logging with `synchronous=NORMAL`: the last commits before a power cut can be lost. Run one service process per database file.
- The runner's isolation self-checks run in a background thread at startup; /health reports them as pending until they finish.
- With `REFACTOR_AI_REFACTOR_USE_ADAPTER=true` and no adapter configured, /health reports `provider.ready: false` with the plain reason. In local mode the model warms up in a background thread at startup; /health answers during the load and submitted runs stay `queued` until it finishes.

## Dataset record

`datasets/guard_clauses/v1/records.jsonl` keeps the validator fields (`id`, `source_group`, `split`, `prompt`, `completion`, `license`, `refactoring_type`) plus `original_code`, `target_code`, `function_name`, `tests` (a list of `ReferenceTest`), `source`, `source_url`, `provenance`, `prompt_version` and `task_version`. A source group never crosses splits.

## Evaluation arms

| Arm | WorkflowSettings |
|---|---|
| A | `mode=single_role`, `refactor_use_adapter=false` |
| B | `mode=multi_role`, `refactor_use_adapter=false` |
| C | `mode=single_role`, `refactor_use_adapter=true` |
| D | `mode=multi_role`, `refactor_use_adapter=true` (analysis and review use the base model) |
