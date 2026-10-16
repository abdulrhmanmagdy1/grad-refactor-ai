# Proposed component contracts

These are concrete starting contracts for T11, not claims about existing endpoints. Reconcile with the SRS and record accepted changes in docs/architecture/decisions.md. Publish example JSON and contract tests before consumers diverge.

## Model provider

A shared provider exposes generate(role, messages, generation_config, model_reference) returning text, model revision, adapter revision or null, elapsed time, token counts when available, and a typed error. Use a pinned base model and optional adapter through the same interface. Bound input tokens, generated tokens, queue wait and overall execution time. A caller timeout must not leave indefinite inference running; use a worker process with termination/restart if the backend cannot cancel generation. Serialize access on one laptop.

FakeProvider is test-only, deterministic, and reported as provider_mode=fake everywhere. LocalProvider reports provider_mode=local_model. Training is a separate offline process. Loading an adapter failure never silently falls back without a recorded warning and explicit model identity.

## Roles

AnalysisResult: schema_version, supported_task, findings (type, start_line, end_line, reason), unsupported_reason or null.

RefactorProposal: schema_version, task_type, proposed_code, explanation, changed_lines, error or null. The application recomputes the diff from original/proposed code; never trust a model-supplied diff as file instructions.

ReviewResult: schema_version, verdict (accept, reject, uncertain), reasons and suggested_correction or null. The model's accept verdict is not proof of behavioral equivalence. Parse strict schemas; treat code fences and malformed output predictably; allow only a bounded repair, never open-ended retries.

Coordinator: validate -> analyze -> generate -> verify -> optional single correction -> final. A supported no-change outcome is distinct from failure. Store per-stage timing, attempt number and stop reason. Total generation calls are bounded: three initial role calls plus at most one repeated generation and review, for a maximum of five. Deterministic tests run after the final candidate as well as any candidate used for correction feedback. Any change to this budget requires protocol versioning.

## Planned run API

- POST /runs: accepts code, task_type and optional allowlisted reference_case_id; returns 202 with run_id, status and polling URL. It accepts no shell commands, filesystem paths, arbitrary test scripts or model download URLs.
- GET /runs/{run_id}: returns the stored run state and result; unknown IDs return 404.
- GET /runs: optional bounded local history, without exposing host paths or secrets.
- GET /runs/{run_id}/proposal: optional download of the proposal with safe Content-Disposition; unavailable proposals return a clear error.

Do not add automatic host-file acceptance actions. Download after human inspection is enough for the first release. Existing /api/v1/analyze remains static and clearly labeled.

Run states: queued -> analyzing -> generating -> verifying -> completed or failed. A single correction may transition verifying -> generating once. On restart, persisted nonterminal runs become failed with interrupted and their evidence retained; do not silently rerun them. Expose a busy error (429 or 503) when the bounded queue is full. Decide exact HTTP error schemas in T11 and test them.

A run record includes schema_version, run_id, created_at, finished_at, status, original_code, proposed_code or null, task_type, model/adapter references, provider_mode, generation settings, attempt_count, stage timings, findings, explanation, diff, verification and error. SQLite writes are atomic. Retain local input only according to a documented retention/delete policy; do not commit user submissions.

## Verification result

Represent syntax as pass/fail; reference tests as pass/fail/not_available/not_run/error; model review as accept/reject/uncertain/error. Record test counts and explicit reasons. Overall disposition is proposal_ready, rejected, uncertain, no_change or failed, separate from whether the workflow completed. Missing tests cannot produce verified or behavior-preserving certainty. Never present a test result as proof for all possible inputs.

The runner accepts a server-owned trusted fixture ID and candidate text through a controlled channel. No caller-chosen paths. It executes outside the API with timeout, memory/CPU/process bounds, no network/secrets/host mounts/Docker socket, non-root and cleanup. Missing isolation support keeps execution disabled.

## Frontend and experiment records

The UI polls boundedly, stops on terminal status and displays interrupted/error cases. Show original/proposed panes or a readable unified diff, explanation, each verification dimension and exact model mode. Preserve input after failures. Do not label fake output as AI success. Limit downloads to the proposal text; no direct repository mutation.

Each experiment attempt includes case_id, split/version, method A/B/C/D, model and adapter revisions, seed/settings, call/token budgets, attempt index, raw output or sanitized reference, parse outcome, syntax result, test availability/outcomes, task rubric result, runtime, available memory metrics, error and stop reason. Missing measurements are null with reason, never zero by assumption.
