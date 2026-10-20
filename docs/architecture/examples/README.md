# Contract examples

Example JSON for each HTTP request and response and for the role outputs, generated from the models in [src/refactor_ai/contracts.py](../../../src/refactor_ai/contracts.py) and from the service's own record and error helpers by [scripts/export_contract_examples.py](../../../scripts/export_contract_examples.py). [tests/test_contract_examples.py](../../../tests/test_contract_examples.py) validates every file against its model and fails when a file is missing, stale or unexpected, so the examples cannot drift from the code. The [contracts page](../contracts.md) explains the fields.

Regenerate after changing a contract model, the task module, the coordinator's output or an error message:

```bash
python -m uv run python scripts/export_contract_examples.py
python -m uv run python scripts/export_contract_examples.py --check
python -m uv run python scripts/export_contract_examples.py --verify-runner
```

## What the values mean

The examples illustrate the schema; none of them is a model result. The completed and failed run records are produced by the real coordinator (`refactor_ai.agents.coordinator.run_workflow`) with the deterministic fake provider, whose texts start with `FAKE PROVIDER (not a model):`, so stop reasons, warnings, disposition reasons and the diff format are the implementation's own. Reference-test results are replayed from results captured from the real reference runner; `python -m uv run python scripts/export_contract_examples.py --verify-runner` runs the real runner again and compares. Timings and run identifiers are fixed values. The local-model identity in the `health_local*.json` files is a placeholder, and the two reference cases are written for this page and are not the demonstration fixture.

## Files

| File | Model | Used by |
|---|---|---|
| `run_create_request.json` | `RunCreateRequest` | POST /api/v1/runs body |
| `run_accepted.json` | `RunAccepted` | POST /api/v1/runs, 202 |
| `run_record_queued.json`, `run_record_analyzing.json` | `RunRecord` | GET /api/v1/runs/{run_id} while a run waits or runs |
| `run_record_proposal_ready.json` | `RunRecord` | Completed, all checks passed, human decision recorded |
| `run_record_uncertain.json` | `RunRecord` | Completed single-role run without reference tests |
| `run_record_no_change.json` | `RunRecord` | Input outside the supported task, zero model calls |
| `run_record_rejected.json` | `RunRecord` | Rubric passed but a reference test failed, also after the correction |
| `run_record_failed.json` | `RunRecord` | Provider timeout during generation |
| `run_record_adapter_unavailable.json` | `RunRecord` | Adapter requested (`REFACTOR_AI_REFACTOR_USE_ADAPTER=true`) but none configured; failed before any model call |
| `run_record_interrupted.json` | `RunRecord` | Marked `failed` with error code `interrupted` at restart |
| `run_list.json` | `RunList` | GET /api/v1/runs |
| `decision_request.json` | `DecisionRequest` | POST /api/v1/runs/{run_id}/decision body |
| `reference_cases.json` | list of `ReferenceCaseSummary` | GET /api/v1/reference-cases |
| `health_fake.json`, `health_local.json` | `HealthResponse` | GET /health in fake mode, and in local-model mode with the adapter in use |
| `health_local_loading.json` | `HealthResponse` | Local model still loading in the background after startup |
| `health_local_adapter_missing.json` | `HealthResponse` | Adapter requested but the provider has none: `ready` is false and the detail says so |
| `analysis_report.json` | `AnalysisReport` | Analysis-role output |
| `review_result.json` | `ReviewResult` | Review-role output |
| `analyze_response.json` | `AnalysisResult` (analysis.py) | POST /api/v1/analyze |
| `error_*.json` | `ErrorResponse` | Error bodies: `validation_error`, `invalid_syntax`, `unknown_reference_case`, `reference_case_mismatch`, `busy`, `run_not_found`, `proposal_unavailable`, `payload_too_large`, `internal_error` |

The full error-code table, with status codes, is in the [backend notes](../../report/notes/backend.md).
