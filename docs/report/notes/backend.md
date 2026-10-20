# Backend and integration notes

Workstream: backend and integration (owner Abdelrahman Magdy). Tasks: T11 example JSON and contract tests, T15 run API and state records. Written on 2026-10-20 from the implementation and its tests. Everything below was tested with the deterministic fake provider, scripted stand-ins for the workflow and, where noted, the real coordinator and reference runner. No model was loaded, so nothing here is evidence of model behavior.

## Components

| File | Responsibility |
|---|---|
| `src/refactor_ai/api.py` | App factory `create_app()`, module-level `app` for uvicorn, endpoints, error handlers, CORS, request-size limit, static frontend fallback |
| `src/refactor_ai/config.py` | `Settings` from the `REFACTOR_AI_*` variables, with validation |
| `src/refactor_ai/runs/store.py` | SQLite run history (`RunStore`) |
| `src/refactor_ai/runs/service.py` | Bounded admission and the single worker thread (`RunService`) |
| `src/refactor_ai/runs/records.py` | Pure helpers that create, finish, interrupt and summarize `RunRecord` values |
| `src/refactor_ai/runs/errors.py` | Error codes and the builders shared by the API and the examples |
| `src/refactor_ai/runs/components.py` | Lazy loading of the workflow, local provider, reference runner and demonstration cases |
| `src/refactor_ai/runs/testing.py` | `ScriptedWorkflow`, a test stand-in with the coordinator's signature |
| `scripts/export_contract_examples.py` | Deterministic example JSON in `docs/architecture/examples/` |

## HTTP API

| Method and path | Success | Errors |
|---|---|---|
| GET /health | 200 `HealthResponse` | 503 `service_unavailable` |
| POST /api/v1/analyze | 200 `AnalysisResult` (static, unchanged) | 413, 422 `validation_error` |
| GET /api/v1/reference-cases | 200 list of `ReferenceCaseSummary` | 500 `reference_cases_unavailable` |
| POST /api/v1/runs | 202 `RunAccepted`, `Location` header | 413; 422 `validation_error`, `invalid_syntax`, `unknown_reference_case`, `reference_case_mismatch`; 503 `busy` with `Retry-After: 10` |
| GET /api/v1/runs?limit= | 200 `RunList`, newest first, limit 1-50 (default 20) | 422 `validation_error` |
| GET /api/v1/runs/{run_id} | 200 `RunRecord` | 404 `run_not_found` |
| GET /api/v1/runs/{run_id}/proposal | 200 `text/x-python; charset=utf-8`, `Content-Disposition: attachment; filename="proposal-<run_id>.py"` | 404, 409 `proposal_unavailable` |
| POST /api/v1/runs/{run_id}/decision | 200 updated `RunRecord` | 404, 409 `proposal_unavailable`, 422 |
| DELETE /api/v1/runs/{run_id} | 204, empty body | 404 `run_not_found` |

Every endpoint that needs the run service also answers 503 `service_unavailable` when the application lifespan has not started it. A submission is checked in this order: request schema (`validation_error`), Python syntax (`invalid_syntax`), reference case (`unknown_reference_case`, then `reference_case_mismatch`), queue capacity (`busy`). A rejected submission stores nothing.

Line endings in submitted code are normalized to LF before storage, as Python's tokenizer reads them. A submission with a `reference_case_id` must equal that case's code after line-ending normalization; trailing whitespace at the very end of the text is also ignored, so an editor that adds or drops the final newline does not cause a false mismatch.

A proposal can be downloaded, accepted or rejected once its run has completed with proposed code, whatever the disposition, because the person sees the verification results first. The latest decision wins. The download is the only way a proposal leaves the service; nothing is written to host files.

## Run states and records

`queued -> analyzing -> generating -> verifying -> completed | failed`, with at most one `verifying -> generating` for the correction. The worker sets `started_at` when it takes a run, stores each non-terminal status the workflow reports through `on_status` as it happens, and stores the terminal status together with the outcome and `finished_at` in one transaction. A client that sees `completed` or `failed` therefore always sees the full result. The queue wait is `started_at - created_at`; the workflow's own `stage_timings`, settings, model reference, attempts and errors are stored as returned.

If the workflow raises, the run becomes `failed` with error code `internal_error`, the last reported status as the stage and a message naming only the exception type. The traceback and message stay in the server log. An outcome that does not validate as `WorkflowOutcome` is handled the same way.

## Queue and worker

`REFACTOR_AI_MAX_PENDING` (default 4) bounds the unfinished runs, counting the waiting runs and the one in progress, so `/health` always shows `0 <= pending <= max_pending`. A submission beyond the bound gets 503 `busy` with `Retry-After: 10`. Exactly one worker thread calls the workflow, in submission order, so model inference is serialized; a test checks that no two workflow calls overlap.

## Storage

One SQLite table `runs (run_id PRIMARY KEY, seq, created_at, status, record)` holds the complete `RunRecord` JSON per run, with indexes on `(created_at, seq)` and `status`. `seq` orders runs created within the same clock tick. One connection is shared by the worker and request threads behind a lock, and every write is a `BEGIN IMMEDIATE` transaction, including read-modify-write updates such as decisions and status changes. The database uses write-ahead logging with `synchronous=NORMAL`: transactions stay atomic and the file stays consistent after a crash, but the last commits before a power loss can be lost. With the default rollback journal each commit took about 50 ms on the demonstration laptop. `PRAGMA user_version` records the table layout version; an unknown version stops startup. A stored row that no longer validates is skipped in lists and logged. The database path is never returned by the API. Run one service process per database file.

## Recovery and shutdown

On startup, every stored run that is not `completed` or `failed` becomes `failed` with error code `interrupted`, its last status as the stage and all stored evidence kept. Such runs are never rerun. On shutdown the service stops accepting runs, lets the run in progress finish for up to 10 seconds, then closes the provider (the local provider then stops its worker process, which ends a running generation) and marks waiting runs `interrupted`. If the worker is still busy after a second grace period, the next start marks its run.

## Retention and deletion

`REFACTOR_AI_RETENTION` (default 200) caps stored runs. When a run is created, and at startup, the oldest finished runs are deleted until at most that many runs remain. Unfinished runs are never pruned, so the store can briefly exceed the cap by the runs in flight. DELETE removes a record immediately: a waiting run is then skipped, and a running run's outcome is discarded when the workflow returns (an in-flight model call cannot be cancelled). Run history stays on the local machine under `runs/`, which Git ignores; submissions are never committed.

## Error model

All errors, including FastAPI request-validation errors, unknown routes and wrong methods, use `{"error": {"code", "message", "details"}}`. Validation details list `loc`, `message` and `type` and never echo submitted values.

| Code | Status | When |
|---|---|---|
| `validation_error` | 422 | Schema, size (more than 20,000 characters), blank code, malformed JSON, bad query parameters |
| `invalid_syntax` | 422 | The code does not parse; details give line, column and the parser message |
| `unknown_reference_case` | 422 | The case id is not in the demonstration allowlist |
| `reference_case_mismatch` | 422 | The code differs from the selected case |
| `busy` | 503 | The bounded queue is full; `Retry-After` header |
| `service_unavailable` | 503 | The run service is not running (startup or shutdown) |
| `run_not_found` | 404 | Unknown or malformed run id |
| `proposal_unavailable` | 409 | The run is not finished or has no proposal |
| `reference_cases_unavailable` | 500 | The demonstration case file exists but is invalid |
| `payload_too_large` | 413 | The request body exceeds 1 MiB |
| `not_found`, `method_not_allowed` | 404, 405 | Unknown route; wrong method, with an `Allow` header listing every method of the path |
| `cors_rejected` | 400 | A browser preflight from an origin other than the Vite development server |
| `internal_error` | 500 | Unexpected server error; details only in the server log |

Codes stored in `RunRecord.error` by the service itself are `internal_error`, `interrupted` and `workflow_unavailable`; the workflow reports its own failures (for example `timeout`) with its own codes.

## Safety

The API never executes submitted or generated code (NFR01). It parses input with `ast.parse` only, and parser failures, including inputs nested too deeply for the parser (`MemoryError`, `RecursionError`), become `invalid_syntax`. Tests submit snippets that would write a file if executed, at module level and inside functions, to both `/api/v1/analyze` and `/api/v1/runs`, and assert that the file never appears. Run ids are 32 lowercase hex characters from `uuid4` and are validated before any lookup. Request bodies above 1 MiB are rejected before parsing. CORS allows only `http://127.0.0.1:5173` and `http://localhost:5173`, without credentials. The built frontend is served from `frontend/dist` only for GET or HEAD paths that no route matched and whose first segment is not `api`, `health`, `docs`, `redoc` or `openapi.json`; files outside the build directory are never served. Reasons shown in `/health` replace the user's home directory with `~`.

## Integration with the other workstreams

At startup the service imports `refactor_ai.agents.coordinator.run_workflow`, `refactor_ai.providers.local.LocalProvider.from_config(REFACTOR_AI_MODEL_CONFIG)` (only when `REFACTOR_AI_PROVIDER=local`; it reads the settings and loads the model on the first request), `refactor_ai.verification.create_runner()` (unless `REFACTOR_AI_RUNNER=disabled`) and the demonstration cases through `refactor_ai.verification.CaseRegistry.from_file()`, which owns the rules for `src/refactor_ai/fixtures/demo_cases.json`. `create_app()` accepts each component directly for tests.

When a component is missing it is reported, never replaced by a pretend result: a missing workflow fails each run with `workflow_unavailable`; a missing local provider appears in `/health` as `ready: false` with the reason; a missing runner is reported as disabled with the reason; a missing case file is an empty allowlist, and an invalid one makes GET /api/v1/reference-cases answer `reference_cases_unavailable`.

The real runner runs its isolation self-checks on its first `info()` call and holds a lock meanwhile; on the demonstration laptop that took 9.5 s, with all 19 checks passing. The service therefore reads it once in a background thread at startup and waits for it at most 1 second. Until the reading is available, `/health` reports `enabled: false` with the reason "The reference runner is still running its isolation self-checks", which is true; a run submitted meanwhile simply waits for the runner.

## Known limitations

- A workflow call that never returns blocks the queue; time limits belong to the workflow (`run_timeout_s`) and the provider (per-call timeouts). Shutdown then gives up after its grace periods and the next start marks the run interrupted.
- `HealthResponse` has no field for workflow availability; it appears only in failed runs and the server log.
- The `Retry-After` value is a fixed 10 seconds, not an estimate.

## Evidence

Run from the repository root:

```bash
python -m uv run pytest tests/test_api.py tests/test_api_runs.py tests/test_api_app.py tests/test_runs_store.py tests/test_runs_service.py tests/test_runs_components.py tests/test_runs_config.py tests/test_runs_records.py tests/test_contract_examples.py
python -m uv run python scripts/export_contract_examples.py --check
```

The suites cover every endpoint and error code, polling to completion, the persisted status sequence, queue saturation with `Retry-After`, serialized workflow calls, restarts with interrupted runs (after a clean shutdown and after a stuck worker), retention and deletion, proposal download headers, decision rules, reference-case matching, health in fake and local mode, CORS, the static frontend, oversized and malformed input, and non-execution of submitted code. Three tests run the real coordinator with the fake provider and the runner disabled through POST /api/v1/runs to completion; one of them uses the default wiring, including the real demonstration cases.

A manual check on 2026-10-20 ran the real coordinator, the fake provider and the real reference runner through the API: a multi-role run with a reference case completed as `proposal_ready` (three calls, 3 of 3 reference tests passed), a single-role run without a case as `uncertain`, and an unsupported input as `no_change` with zero calls. A second manual check started uvicorn on port 8765, killed the process while a run was verifying and another was queued, and restarted it on the same database: both runs were reported as `interrupted` with stages `verifying` and `queued`. These checks show the plumbing only; the fake provider's output is not model output.
