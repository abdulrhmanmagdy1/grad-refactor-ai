# Single-laptop agent team allocation

This run of the [execution pack](README.md) uses one coding agent per human workstream, coordinated by an integration agent on the same laptop. Ownership of each workstream stays with the named student, who inspects and explains it before accepting the delivery. Agent work is not a substitute for that inspection or for supervisor meetings.

| Agent workstream | Student owner | Tasks | Owned paths |
|---|---|---|---|
| Coordination and contracts | Abdelrahman Magdy | Step 0, T11 contracts, integration, execution state | `src/refactor_ai/contracts.py`, `task_format.py`, `tasks/`, `providers/base.py`, `providers/fake.py`, `pyproject.toml`, `uv.lock`, `README.md`, `docs/architecture/contracts.md`, `docs/architecture/decisions.md`, `docs/agent-execution/execution-state.json` |
| Backend and integration | Abdelrahman Magdy | T11 examples, T15, T18, T21, T25 | `src/refactor_ai/api.py`, `config.py`, `runs/`, `tests/test_api*.py`, `tests/test_runs*.py`, `tests/test_contract_examples.py`, `docs/architecture/examples/` |
| Agent workflow and verification | Abdullah Tarek | T06, T13, T14, T19, T20, T23 | `src/refactor_ai/agents/`, `src/refactor_ai/verification/`, `tests/test_agents*.py`, `tests/test_verification*.py`, `tests/test_runner*.py`, `docs/requirements/task-scope.md`, `docs/architecture/workflow.md`, `docs/development/runner-safety.md` |
| Models and training | Abdelrahman Adel | T04, T05, T09, T12, T17, T22 | `training/`, `src/refactor_ai/providers/local.py`, `src/refactor_ai/providers/model_worker.py`, `configs/`, `tests/test_local_provider*.py`, `experiments/hardware/`, `experiments/models/`, `experiments/training/`, training plan and model card |
| Data and evaluation | Shahd Abdelhay | T03, T07, T08, T10, T24 | `src/refactor_ai/data/`, `src/refactor_ai/evaluation/`, `src/refactor_ai/fixtures/demo_cases.json`, `datasets/`, `scripts/curate_dataset.py`, `scripts/evaluate.py`, `scripts/validate_dataset.py`, `tests/test_data*.py`, `tests/test_evaluation*.py`, `experiments/data/`, `experiments/evaluation/`, related work, data plan and protocol |
| Frontend and delivery | Dania El-Walily | T16, T26, T27 | `frontend/`, `docs/development/frontend.md`, `docs/delivery/`, `docs/report/` |
| Independent quality review | All owners inspect | T23 support, T25 support | Review findings only; fixes return to the owning workstream |

Each workstream writes its technical notes in `docs/report/notes/<workstream>.md` for the report.

## Shared rules

- English for all repository content. No commits, pushes, Issue or Project changes without the current human session's authorization.
- Edit only owned paths. Request changes to another workstream's files through the coordinator.
- Run `python -m uv run ruff format <own paths>` and `ruff check <own paths>`; repository-wide formatting is run by the coordinator only. Run the full test suite freely.
- Core dependencies change only through the coordinator. The training environment lives in `.venv-train/`, model weights in `models/`, generated runs in `runs/`; all are ignored by Git.
- One GPU with 4 GB VRAM: only the models workstream uses it until the coordinator schedules evaluation. Never run training and inference at the same time.
- Disk is limited (about 9 GB free at kickoff). Keep at least 1.5 GB free and delete only files you created.
- Never fabricate measurements, data provenance, citations, test results or approvals. The fake provider's output is never evidence of model behavior.
- Stop only processes you started. Never stop editors, Claude sessions or unrelated Node or Python processes.

## Waves

1. Contracts, then parallel foundations: environment and model measurements; task scope, roles, verification and runner on the fake provider; related work, curated data and frozen splits; run API and storage; the web interface on the documented contracts.
2. Integration on the real model: baseline and adapter training on the train split, validation-only selection, coordinator on the local provider, evaluation harness dry run on validation data, verification display.
3. Independent quality review and acceptance matrix, then the frozen test-split evaluation, clean-clone reproduction, report, slides and demonstration.
