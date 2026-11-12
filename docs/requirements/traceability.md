# Requirements traceability matrix

Maps every requirement in the [SRS](srs.md) to its implementation, tests and status. Statuses:
**Implemented** (foundation behavior exists and is tested), **Partial** (present with a stated
limit), **Deferred** (planned, not yet built), **Excluded** (out of this release).

Test paths are relative to the repository root; run everything with `uv run pytest`.

## Functional requirements

| ID | Requirement | Implementation | Tests | Status |
|---|---|---|---|---|
| FR01 | Accept bounded Python input | `src/core/schemas.py` (`CodeInput`, `CreateRunRequest`), `src/api/middleware.py` | `tests/test_api.py::test_invalid_syntax_and_empty_input`, `tests/test_runs_api.py::test_analyze_endpoint_rejects_empty_and_oversized` | Implemented |
| FR02 | Analyze code | `src/core/ast_analyzer.py` (findings + structural metrics + AST constellation graph), `src/agents/analysis_agent.py` (structured AnalysisPlan) | `tests/test_ast_analyzer.py`, `tests/test_api.py::test_long_async_function`, `tests/test_api.py::test_nesting_is_structural_not_indentation` | Implemented |
| FR03 | Propose a refactoring (code, reason, type, or explicit failure) | `src/agents/refactoring_agent.py` (explicit system contract + critique-driven retry), `src/agents/orchestrator.py`, `src/core/schemas.py` (`RunRecord.refactoring_type`), `src/core/db.py` (upsert so the background worker can claim a queued run) | `tests/test_agents.py`, `tests/test_runs_api.py::test_requested_refactoring_type_is_echoed`, `tests/test_async_run.py` (async path reaches a terminal state) | Implemented |
| FR04 | Verify a proposal (syntax + tests separate from verdict) | `src/agents/review_agent.py` (3-layer review incl. MI regression guard, verdicts approved/rejected/uncertain), `src/runner/test_generator.py` (auto golden equivalence tests), `src/runner/sandbox.py`, `VerificationResult` | `tests/test_sandbox.py`, `tests/test_agents.py::test_sandbox_test_verification_integration` | Implemented |
| FR05 | Show a diff (added/removed lines + components) | `src/core/diff_utils.py` (diff + signature extraction), `DiffOutput` | `tests/test_runs_api.py::test_create_and_poll_run_sync` | Implemented |
| FR06 | Preserve user control (accept/reject/download) | `src/api/routes.py` feedback endpoint + `/decision` alias; `frontend/src/components/tabs/VerificationView.tsx` (accept/reject), `ResultsPanel.tsx` (copy/download) | `tests/test_runs_api.py::test_user_feedback_acceptance_and_rejection` | Implemented |
| FR07 | Trace each run (id, config, model version, state, duration, failures) | `src/core/db.py` (extra JSON columns + idempotent migration, upsert for the background worker, startup recovery of non-terminal runs with an explicit diagnostic), `RunRecord` (agent traces, metrics snapshots, AST graphs, auto tests), orchestrator metrics, `src/api/reports.py` (Markdown report from the stored record), `src/api/middleware.py` (`X-Request-ID` + timing headers per response), `frontend/src/features/compare/CompareDialog.tsx` (two-run comparison), `frontend/src/features/history/historyExport.ts` (JSON/CSV export) | `tests/test_agents.py`, `tests/test_runs_api.py`, `tests/test_reports_api.py`, `tests/test_middleware.py`, `tests/test_operations.py::test_recovery_marks_runs_left_in_flight_as_failed`, `frontend/src/features/history/historyExport.test.ts` | Implemented |
| FR08 | Enforce bounded limits on model calls, tokens, retries and duration | `CreateRunRequest` (bounded fields), `src/agents/orchestrator.py` (limit enforcement with explicit failure reasons), `src/api/middleware.py` (payload ceiling) | `tests/test_agents.py` (limit failures), `tests/test_runs_api.py::test_fr08_token_limit_fails_clearly`, `frontend/src/features/workspace/WorkspacePanel.tsx` (FR08 budgets exposed in the UI) | Implemented |
| FR09 | Compare experiments (same cases, export) | `src/evaluation/harness.py` (groups A–D, dataset mode, findings/clean variants, `refactor_success` + rule-resolution metrics, base/mock baseline, best-of-N hookup, `--include-code` source export), `src/evaluation/metrics.py` (CodeBLEU + AST similarity), `src/core/candidate_selection.py` (AST-only candidate choice), outputs in `experiments/` | `tests/test_evaluation.py`, `tests/test_blind_review.py`, `tests/test_prompting_and_selection.py` | Implemented (real 3B base vs fp16 LoRA A–D executed on Kaggle T4 in `experiments/dataset_test_finetuned_*`, 0 `provider_unavailable`; mock baseline preserved in `experiments/dataset_test_*`) |
| FR10 | Retain run history | `src/core/db.py` (`list_runs`, `count_runs`, `run_statistics`), `GET /runs` (limit up to 500 + `offset` + `X-Total-Count`), `GET /api/v1/stats`, `frontend/src/features/insights/InsightsPanel.tsx` (measured aggregates + recent-run bars), `frontend/src/features/history/HistoryDrawer.tsx` (honest "showing N of M" paging), `scripts/prune_runs.py` (dry-run retention window) | `tests/test_runs_api.py::test_list_runs_history`, `tests/test_operations.py::test_stats_report_measured_aggregates`, `tests/test_operations.py::test_run_list_carries_an_honest_total_count`, `tests/test_prune_runs.py`, `frontend/src/features/history/HistoryDrawer.test.tsx` | Implemented |

## Quality requirements

| ID | Requirement | Implementation / evidence | Status |
|---|---|---|---|
| NFR01 | API must not execute submitted/generated code | `src/core/ast_analyzer.py` (AST only); `tests/test_api.py::test_analysis_does_not_execute_code`, `tests/test_runs_api.py::test_analyze_endpoint_does_not_execute_code` | Implemented |
| NFR02 | No untrusted or unsafe execution path | AST-only inspection in the API process; tests run only in `src/runner/sandbox.py`; `src/api/middleware.py` (body-size limit, `Content-Security-Policy` with `script-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`, `Permissions-Policy`) | `tests/test_middleware.py::test_responses_carry_a_strict_content_security_policy`, `tests/test_api.py::test_analysis_does_not_execute_code`, `tests/test_sandbox.py` | Implemented |
| NFR03 | No paid API or committed credentials | Zero-dependency core; `.env.example`; no keys in repo; all providers are local (mock / smart_ast / ollama / local LoRA) | Implemented |
| NFR04 | Python 3.11 + lockfile; separate GPU deps | `.python-version`, `pyproject.toml`, `uv.lock`, `training/requirements.in` (QLoRA: torch/transformers/peft/accelerate/datasets/bitsandbytes) | Implemented |
| NFR05 | Experiment records identify code/data/model/config/seed/hardware | `experiments/run-template.json`, `experiments/*_results.csv` + `*_summary.json` (generated), `data/manifest.json` (sha256 + split/type/findings/clean counts + per-record verification), `training/train_lora.py` (`run-manifest.json`: dataset sha256, resolved model commit, packages, hardware, seed, peak GPU memory, adapter checksums, AST-only smoke generation), `RELEASE_MANIFEST.json` + `scripts/verify_release.py` (sha256 + aggregate digests of dataset, experiments and the committed UI bundle) | Implemented (populated in Kaggle `runs/lora-fp16/run-manifest.json` and `experiments/dataset_test_finetuned_*`) |
| NFR06 | Passing tests are not full behavioral equivalence | `VerificationResult` separation; three-verdict review; `provider_unavailable` rows with null aggregates instead of fabricated rates; `scripts/aggregate_blind_review.py` refuses to summarise before humans rate; report sections state absent evidence explicitly; docs | Implemented (documented policy) |
| NFR07 | Set latency/memory targets after measurement (P1) | `GET /metrics` exposes the measured mean/median duration, in-flight count and acceptance rate from the stored runs (dependency-free Prometheus text format) so the targets can be set from numbers, not guesses; the targets themselves remain **Deferred** until the final test evaluation | Partially implemented (measurement surface) |

## Use cases

| ID | Use case | Coverage |
|---|---|---|
| UC01 | Submit a valid example, inspect the proposal, download an accepted result | `tests/test_runs_api.py` (run + feedback), `frontend/src/features/results/ResultsPanel.tsx` (diff, accept/reject, copy/download, Markdown report export), `frontend/src/features/results/DiffViewer.tsx` (Monaco diff), `tests/test_reports_api.py` |
| UC02 | Submit invalid Python and get an error without execution | `tests/test_api.py::test_invalid_syntax_and_empty_input` |
| UC03 | Encounter a failure and see a clear reason, not a success indicator | `tests/test_agents.py::test_bounded_correction_loop_exhaustion`, `tests/test_runs_api.py::test_fr08_token_limit_fails_clearly`, `tests/test_operations.py::test_recovery_marks_runs_left_in_flight_as_failed` (a run interrupted by a restart is failed with an explicit diagnostic, never left alive) |
| UC04 | Run a comparison experiment and export records + summary | `tests/test_evaluation.py`, `src/evaluation/harness.py`, real outputs in `experiments/` (`evaluation_results.csv`/`evaluation_summary.json`, `dataset_test_results.csv`/`dataset_test_summary.json`), blinded packet + aggregation tooling (`scripts/prepare_blind_review.py`, `scripts/aggregate_blind_review.py`, `tests/test_blind_review.py`) |

## Architecture decisions

ADR01–ADR19 are recorded in [`../architecture/decisions.md`](../architecture/decisions.md) and
realized in code: Python input (ADR01), fine-tune existing model (ADR02), GitHub collaboration
(ADR03), local-only/zero budget (ADR04), repository ownership (ADR05), Python 3.11 + uv + FastAPI
(ADR06), modification-role first (ADR07), small open-weight model + LoRA (ADR08), SQLite run
history (ADR09), explicit workflow before an agent framework (ADR10), GitHub artifact storage
checks (ADR11), honest local provider ladder (ADR12), sandbox-verified dataset and auto golden
tests (ADR13), single professional React UI bound to real API data with dark/light themes (ADR14),
release manifest with sha256 checksums and LF normalization (ADR15), Markdown run reports and
request tracing headers (ADR16), layered web client with Zod-validated contracts and query-managed
server state (ADR17), strict content-security policy, exposed FR08 budgets, two-run comparison and history export (ADR18), operational surface with JSON logs, Prometheus metrics, a concurrency guard and the contract drift check (ADR19).

## Deferred and excluded (this release)

- **Deferred:** 4-bit QLoRA verification (Kaggle training/eval ran cleanly as native **fp16 LoRA** while 4-bit loading remained unproven on that image); NFR07 measured latency targets sign-off; blind human review ratings (the 4-candidate A–D packet is regenerated under `experiments/review/`, waiting for human scores in `score_sheet.csv`); second-machine clean-clone verification (`scripts/verify_release.py` against the updated `RELEASE_MANIFEST.json`).
- **Excluded:** training a model from scratch; multiple languages; large repositories; automatic
  GitHub branch edits; guaranteed behavioral equivalence; public hosting; paid services; executing
  untrusted code in the API.
