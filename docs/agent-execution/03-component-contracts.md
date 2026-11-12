# 03 — Component contracts

These contracts mirror `src/core/schemas.py`, `src/api/routes.py` and the agent interfaces. They
are the agreed shapes roles exchange; any change is an experimental/architectural decision and
must be recorded in [`decisions.md`](../architecture/decisions.md).

## HTTP surface

| Method | Endpoint | Purpose | Requirement |
|---|---|---|---|
| `GET` | `/health` | Service health, version, `production` mode | — |
| `POST` | `/api/v1/analyze` | Static AST heuristics; never executes code | FR02, NFR01 |
| `GET` | `/api/v1/providers` | Live provider availability catalog | Phase 6 |
| `POST` | `/runs` | Start a run (`?sync=true` runs inline) | FR03, FR07 |
| `GET` | `/runs/{id}` | Poll state, metrics, diff, verification, traces, graphs | FR07 |
| `GET` | `/runs/{id}/report` | Markdown report rendered from the stored record (inline, or `?download=true`); absent sections are stated explicitly | FR07, NFR06 |
| `GET` | `/runs` | List run history | FR10 |
| `POST` | `/runs/{id}/feedback` | Record acceptance or rejection (`/decision` alias) | FR06 |
| `GET` | `/` and `/docs` | Single-page React UI, generated API reference | — |

Every response also carries `X-Request-ID` (echoed when the caller sends a well-formed id,
otherwise minted) and `X-Process-Time-Ms`; API paths are logged with both, so a run shown in the
UI can be traced to its server log line.

## Request records

`CodeInput` — `code: str` (non-blank, `1..20000` chars). Rejects oversized/malformed input with a
422 and an understandable message (FR01).

`CreateRunRequest` — `code` (bounded), optional `test_code`, optional `refactoring_type`,
`provider` (`mock` | `smart_ast` | `ollama` | `local` | `local_lora` | `auto`), and the FR08
boundaries: `max_retries` (0–1), `max_model_calls` (1–4), `max_total_tokens` (1–100000),
`max_duration_seconds` (>0, ≤600).

## Result records

`AnalysisResult` — `syntax_valid`, `findings[]`, `error`, `engine`, `metrics`, optional
`ast_graph` (structural nodes + edges rendered by the UI graph view). Each `ASTFinding`
carries `rule`, `line`, `end_line`, `node_type`, `message`, `rationale` (FR02).

`ProviderInfo` — `id`, `label`, `available`, `engine`, `detail`; availability is probed live and
a missing adapter is reported as unavailable with remediation hints (ADR12).

`DiffOutput` — `diff`, `original_code`, `refactored_code`, `added_lines`, `removed_lines`,
`modified_components`, `syntax_valid` (FR05).

`VerificationResult` — `syntax_valid`, `tests_available`, `tests_passed`, `review_verdict`
(`approved` | `rejected` | `uncertain`), `review_notes`, `preserved_symbols`,
`critique_feedback`, `auto_generated_tests`, `metrics_before` / `metrics_after` /
`metrics_delta`, `details`. Syntax, test availability/outcome and the verdict stay **separate**
(FR04, NFR06).

`RunRecord` — `id`, `created_at`, `status`, `input_code`, `refactoring_type`, `output_code`,
`diff`, `explanation`, `metrics`, `metrics_before` / `metrics_after` / `metrics_delta`,
`agent_traces[]`, `auto_generated_tests`, `ast_graph_before` / `ast_graph_after`, `errors`,
`user_feedback`, `feedback_comment`, `verification`, `findings` (FR03, FR07, FR10).

## Run states

```
queued → analyzing → generating → verifying → completed
                                   └────────→ failed
```

Any stage may transition to `failed` with a diagnostic in `errors`. A failed or uncertain check
never produces a misleading success indicator (UC03).

## Role interfaces

- `AnalysisAgent.analyze(code) -> AnalysisResult`; `formulate_goal(findings) -> str`.
- `RefactoringAgent.refactor(code, findings, retry_feedback, options) -> (code, metadata)`;
  `explain(original, refactored, diff) -> str`.
- `ReviewAgent.review(original, candidate, test_code) -> (VerificationResult, DiffOutput)`.
- `BaseModelProvider.generate_refactoring(...)` and `explain_changes(...)`; implementations:
  `MockModelProvider` (deterministic, default) and `LocalModelProvider` (HF + PEFT/LoRA, CPU
  fallback).
- `WorkflowOrchestrator.execute_run(request, run_id) -> RunRecord` (bounded correction loop,
  max one retry, FR08 boundaries).

## Failure behavior

| Failure | Behavior |
|---|---|
| Invalid/blank/oversized input | Rejected before execution with a clear message (FR01, UC02) |
| Invalid candidate syntax | `review_verdict = rejected`, reason recorded (FR04, UC03) |
| Missing original symbols | `preserved_symbols = False`, rejected |
| Trusted test failure/timeout | `tests_passed = False`, reason recorded; timeout noted (FR08, NFR02) |
| Model/inference timeout | Explicit failure, no success indicator (UC03) |
| Declared limit exceeded (calls/tokens/time) | Run `failed` with an explicit limit message (FR08) |

## Trust boundary (NFR01, NFR02)

The FastAPI process and agent engine never execute submitted or candidate code; inspection is
strictly AST-based. Test execution, when enabled, happens only in `IsolatedRunner` — a separate
subprocess with a timeout, memory/CPU limits, a sanitized environment, an isolated temporary
directory and cleanup — and only for trusted examples.
