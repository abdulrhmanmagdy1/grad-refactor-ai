# Implementation handover

Prepared on 2026-10-21 for the team's inspection, as required by [acceptance and handover](../agent-execution/06-acceptance-and-handover.md). The implementation was produced by AI coding agents on the demonstration laptop, one agent per workstream plus a coordinator, following the [agent execution pack](../agent-execution/README.md). Nothing here is accepted until each owner has inspected their workstream; no supervisor review has taken place.

## Version

Branch `main` on GitHub (`abdulrhmanmagdy1/grad-refactor-ai`). Every code commit was checked in a clean worktree before it was pushed; three commits with only records and documentation (`911ca3c`, `dd1b0fa`, `90462d3`) were checked by the link checker and CI instead, and GitHub Actions passed for every push ([verification record](../../experiments/qa/2026-10-21-clean-worktree-verification.md)). A clean clone from GitHub at `74daf25` passed every check, the dataset rebuild and a complete run ([clean-clone record](../../experiments/qa/2026-10-21-clean-clone-reproduction.md)). The frozen evaluation ran from commit `9582c66`; the latest state is the head of `main`.

## Commands

| Goal | Command |
|---|---|
| Install the core environment | `uv sync --frozen` (Python 3.11) |
| Build the web interface | `cd frontend && npm ci && npm run build` (Node 24.12) |
| Start in fake mode (no model) | `uv run uvicorn refactor_ai.api:app --host 127.0.0.1` and open http://127.0.0.1:8000 |
| Start with the fine-tuned model | Set `REFACTOR_AI_PROVIDER=local`, `REFACTOR_AI_MODEL_CONFIG=configs/model.local.json`, `REFACTOR_AI_REFACTOR_USE_ADAPTER=true`, then start as above ([setup](../development/setup.md)) |
| Run the checks | `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`, `uv run python scripts/check_docs.py`; in `frontend/`: `npm run typecheck`, `npm test` |
| Rebuild the dataset and confirm it is unchanged | `uv run python scripts/curate_dataset.py --check` |
| Train or evaluate on Kaggle | `python training/kaggle/lane.py bundle/upload/push/wait/fetch` ([Kaggle lane](../../training/kaggle/README.md)) |
| Report an evaluation | `uv run python scripts/report_evaluation.py <records.jsonl> --out <dir> --targets experiments/evaluation/protocol-freeze.json` |

The training environment (`.venv-train`, CUDA 12.6) and the model weights (`models/`) are not in Git; [training/requirements-cuda.txt](../../training/requirements-cuda.txt) and the [model card](../data-and-training/model-card.md) give the exact versions and checksums.

## Hardware and environment

Demonstration laptop: Windows 11, AMD Ryzen 7 7435HS, 7.8 GB RAM, NVIDIA RTX 2050 with 4 GB ([hardware record](../../experiments/hardware/2026-10-20-demonstration-laptop.json)). Training and the evaluations ran on Kaggle's free Tesla T4 in float32; the laptop serves the adapter in bf16.

## Component map

| Area | Code | Owner |
|---|---|---|
| Contracts, task definition, prompt format | `src/refactor_ai/contracts.py`, `tasks/`, `task_format.py`, `providers/base.py`, `providers/fake.py` | Abdelrahman Magdy |
| Run API, storage, queue | `src/refactor_ai/api.py`, `config.py`, `runs/` | Abdelrahman Magdy |
| Roles, coordinator, verification, runner | `src/refactor_ai/agents/`, `verification/` | Abdullah Tarek |
| Model provider, training, Kaggle lane | `src/refactor_ai/providers/local.py`, `model_worker.py`, `training/` | Abdelrahman Adel |
| Dataset, evaluation harness | `src/refactor_ai/data/`, `evaluation/`, `datasets/`, `scripts/` | Shahd Abdelhay |
| Web interface, report, delivery materials | `frontend/`, `docs/report/`, `docs/delivery/` | Dania El-Walily |

## Task, model, data and results

- Task: `guard_clauses` (replace nested conditionals with guard clauses), one function of at most 3,000 characters and 60 lines ([task scope](../requirements/task-scope.md)).
- Model: Qwen/Qwen2.5-Coder-0.5B-Instruct at revision `ea3f2471`, Apache-2.0; LoRA adapter `full-2026-10-21`, weights sha256 `dff9ae02…` ([model card](../data-and-training/model-card.md), [training record](../../experiments/training/full-2026-10-21.json)).
- Data: 799 records (627 train, 84 validation, 88 test), test split frozen with content hash `3a1e6b95…` ([data plan](../data-and-training/data-plan.md)).
- Results on the frozen test split, N = 88 per arm: accepted A 7, B 1, C 70, D 35; 11 of 12 pre-registered targets met ([results](../../experiments/evaluation/test-2026-10-21/targets-report/summary.md), [report](../report/report.md)).

## Known defects and limits

- The multi-role review uses the original model and often repeats itself until the 384-token limit, so its verdict becomes an error and the outcome `uncertain`.
- The reference runner is a hardening layer for server-owned cases, not a sandbox for hostile code ([runner safety](../development/runner-safety.md)).
- Code pasted by a user has no reference tests, so it can at best end as `uncertain`.
- Reproduction was checked only on the demonstration laptop (a same-laptop clean clone); a second machine is untested.
- The adapter and the team-authored data are not published; their redistribution terms are a team decision.

## Pending human decisions

The five supervisor reviews ([packs](../supervisor-reviews/README.md)), the university template and dates, the data license, whether to publish the adapter, and each owner's acceptance of their workstream. The release is not tagged; its notes are drafted in [release-notes-draft.md](release-notes-draft.md).

## What each owner should inspect

| Owner | Inspect and be able to explain |
|---|---|
| Abdelrahman Magdy | Setup, API, storage, recovery, the contracts, the release |
| Abdullah Tarek | Role prompts, coordinator budgets and correction, verification, the runner's isolation checks, the [acceptance matrix](acceptance-matrix.md) |
| Abdelrahman Adel | Model choice, the prompt-format study, training on Kaggle, adapter checksums, the provider |
| Shahd Abdelhay | Data provenance and licenses, splits and leakage checks, the frozen protocol, targets and results |
| Dania El-Walily | The interface states, the [report](../report/report.md), the [demo script](demo-script.md) and the [slides](slides/grad-refactor-ai-presentation.pptx) |
