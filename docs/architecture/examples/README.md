# Contract examples

Example JSON for each HTTP request and response and for the role outputs, generated from the models in [src/refactor_ai/contracts.py](../../../src/refactor_ai/contracts.py) and from the service's own record and error helpers by [scripts/export_contract_examples.py](../../../scripts/export_contract_examples.py). [tests/test_contract_examples.py](../../../tests/test_contract_examples.py) validates every file against its model and fails when a file is missing, stale or unexpected, so the examples cannot drift from the code. The [contracts page](../contracts.md) explains the fields.

Regenerate after changing a contract model, the task module or an error message:

```bash
python -m uv run python scripts/export_contract_examples.py
python -m uv run python scripts/export_contract_examples.py --check
```

## What the values mean

The examples illustrate the schema; none of them is a result. Run records use the deterministic fake provider, whose texts start with `FAKE PROVIDER (not a model):`. The local-model identity in `health_local.json` is a placeholder, and the two reference cases are written for this page and are not the demonstration fixture. Timings, token counts and run identifiers are invented. Values that other components choose (stop reasons, diff headers, the changed-line numbering, isolation check names and reason texts) show the shape only; the workflow and the runner define them.

## Files

| File | Model | Used by |
|---|---|---|
| `run_create_request.json` | `RunCreateRequest` | POST /api/v1/runs body |
| `run_accepted.json` | `RunAccepted` | POST /api/v1/runs, 202 |
| `run_record_queued.json`, `run_record_analyzing.json` | `RunRecord` | GET /api/v1/runs/{run_id} while a run waits or runs |
| `run_record_proposal_ready.json` | `RunRecord` | Completed, all checks passed, human decision recorded |
| `run_record_uncertain.json` | `RunRecord` | Completed single-role run without reference tests |
| `run_record_no_change.json` | `RunRecord` | Input outside the supported task, zero model calls |
| `run_record_rejected.json` | `RunRecord` | Rubric passed but a reference test failed after the correction |
| `run_record_failed.json` | `RunRecord` | Provider timeout during generation |
| `run_record_interrupted.json` | `RunRecord` | Marked `failed` with error code `interrupted` at restart |
| `run_list.json` | `RunList` | GET /api/v1/runs |
| `decision_request.json` | `DecisionRequest` | POST /api/v1/runs/{run_id}/decision body |
| `reference_cases.json` | list of `ReferenceCaseSummary` | GET /api/v1/reference-cases |
| `health_fake.json`, `health_local.json` | `HealthResponse` | GET /health in fake and local-model mode |
| `analysis_report.json` | `AnalysisReport` | Analysis-role output |
| `review_result.json` | `ReviewResult` | Review-role output |
| `analyze_response.json` | `AnalysisResult` (analysis.py) | POST /api/v1/analyze |
| `error_*.json` | `ErrorResponse` | Error bodies: `validation_error`, `invalid_syntax`, `unknown_reference_case`, `reference_case_mismatch`, `busy`, `run_not_found`, `proposal_unavailable`, `payload_too_large`, `internal_error` |

The full error-code table, with status codes, is in the [backend notes](../../report/notes/backend.md).
