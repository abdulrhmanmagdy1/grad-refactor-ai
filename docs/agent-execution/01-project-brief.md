# 01 — Project brief

## Goal

Deliver a reproducible, locally runnable multi-agent workflow that proposes, verifies and
presents bounded Python refactorings, and an empirical comparison of single-role versus
coordinated roles and of a fine-tuned modification model versus its base model.

Improvement from coordination or fine-tuning is a **hypothesis, not a promised result**. Data
preparation, reproducibility and failure analysis are part of the contribution.

## First-release scope

- Input: one Python function or a small file, non-blank, up to 20,000 characters (`FR01`).
- Static analysis of long functions (including async), deep nesting and high complexity (`FR02`).
- A proposed refactoring with code, a reason and the supported refactoring type, or an explicit
  failure (`FR03`).
- Deterministic verification (syntax, symbol preservation, optional trusted tests) presented
  separately from the model's verdict (`FR04`, `NFR06`).
- A unified diff with added/removed lines and affected components (`FR05`).
- User acceptance, rejection and download without modifying the original input (`FR06`).
- Per-run audit trail: identifier, limits/configuration, model version, state, durations and
  failures (`FR07`, `FR08`).
- A comparison harness over groups A/B/C/D with CSV and JSON export (`FR09`).
- Local run history on the demonstration machine (`FR10`).

## Existing code (foundation already in this repository)

| Area | Location | Status |
|---|---|---|
| FastAPI app + routes | `src/api/` | Implemented (`/health`, `/api/v1/analyze`, `/runs*`) |
| Pydantic v2 contracts | `src/core/schemas.py` | Implemented |
| Static AST engine | `src/core/ast_analyzer.py` | Implemented |
| Diff + symbol utilities | `src/core/diff_utils.py` | Implemented |
| SQLite run store (WAL) | `src/core/db.py` | Implemented |
| Analysis / refactoring / review agents | `src/agents/` | Implemented |
| Orchestrator with bounded retry | `src/agents/orchestrator.py` | Implemented (max 1 retry) |
| Model providers (mock + local/HF) | `src/models/` | Implemented; mock is default |
| Isolated test runner | `src/runner/sandbox.py` | Implemented for trusted examples |
| Evaluation harness | `src/evaluation/harness.py` | Implemented (A/B executed; C/D honest `provider_unavailable`) |
| Web UI | `frontend/` | Implemented (React 19 + TypeScript + Vite) |
| QLoRA training script | `training/train_lora.py` | Implemented path; no training run/adapter yet (needs CUDA) |
| Curated dataset | `data/curated.jsonl` | 416 authored records (224 findings + 192 clean controls) |
| Tests | `tests/` | Unit, integration, sandbox, API, dataset, training, prompting |

A base-model demonstration is useful but **does not satisfy the fine-tuning deliverable**. Never
report a base model as trained.

## Exclusions for this release

- Training a language model from scratch; a real QLoRA run/adapter is still pending CUDA hardware
  (the script and config are implemented).
- Multiple languages, large repositories, automatic GitHub branch edits.
- Guaranteed behavioral equivalence for all programs; public hosting; paid services.
- Executing untrusted code: the runner remains limited to trusted examples.

## Final outcome

An end-to-end prototype, documented data preparation, a recorded fine-tuning experiment, an
evaluation report, developer and user documentation, and a repeatable presentation. Assessment
follows the [evaluation protocol](../evaluation/protocol.md), including negative results.
