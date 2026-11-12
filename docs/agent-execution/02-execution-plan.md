# 02 — Execution plan

Ordered steps for one coding agent on one laptop. Each step lists its destination, dependencies
and the **exit evidence** required before moving on. Keep one primary task active; do not start a
large training run before the hardware gate.

## Step 0 — Inspect and baseline

- Destination: none (read-only), plus a working copy of `execution-state.template.json`.
- Commands: `uv run python scripts/doctor.py`, `uv run pytest`, `uv run ruff check .`.
- Exit evidence: recorded hardware line, test summary, and the current commit SHA in the state file.

## Step 1 — Hardware gate (P1, Day 2)

- Destination: `experiments/` (a small run record) or a documented blocker.
- Do: measure local inference; run a tiny LoRA save/reload smoke test.
- Exit evidence: memory/time numbers, adapter save + reload result, or a written blocker and a
  reduced-scope proposal. Never present a base model as trained.

## Step 2 — Contracts and data records (P2)

- Destination: `src/core/schemas.py`, `docs/architecture/system-design.md`,
  [`03-component-contracts.md`](03-component-contracts.md).
- Dependency: Step 1 (or a recorded blocker).
- Exit evidence: versioned request/result/error schemas; run states; contract tests under `tests/`.

## Step 3 — Data preparation and frozen split (P2, Day 5)

- Destination: `data/`, `scripts/validate_dataset.py`, `experiments/` manifest.
- Commands: `uv run python scripts/validate_dataset.py data/curated.jsonl`.
- Exit evidence: JSONL with `id, source_group, split, prompt, completion, license,
  refactoring_type`; source-separated splits; dataset hash + split manifest; frozen test split.

## Step 4 — Provider and roles converge (P3, Day 10)

- Destination: `src/models/`, `src/agents/`, `src/api/`.
- Dependency: Step 2, Step 3.
- Exit evidence: one real-model input-to-result case; provider swap without changing the API;
  bounded correction loop (at most one retry).

## Step 5 — Verification, UI and failure display (P4, Day 15)

- Destination: `src/runner/sandbox.py`, `src/agents/review_agent.py`, `frontend/`.
- Dependency: Step 4.
- Exit evidence: syntax, available tests and review verdict shown separately; `tests unavailable`
  handled; runner isolation checks (limits, cleanup, no secrets/network) on trusted examples.

## Step 6 — Optional fine-tuning run (P3–P4, if hardware permits)

- Destination: `training/`, `configs/`, `experiments/`.
- Commands: `python training/train_lora.py --config configs/training.local.json`.
- Exit evidence: `run-manifest.json`, `validation-metrics.json`, reloadable adapter + checksum, or a
  recorded blocker. Reject unresolved settings and CPU-only environments.

## Step 7 — Independent evaluation (P5, Days 16–20)

- Destination: `experiments/evaluation_results.csv`, `experiments/evaluation_summary.json`.
- Commands: `uv run python -m evaluation.harness --output-dir experiments`.
- Dependency: Step 3 (frozen test), Step 6 (adapter or recorded blocker).
- Exit evidence: case-level records for groups A/B/C/D including failures and timeouts; summary
  with coverage and counts; numbers traceable to raw records.

## Step 8 — Delivery (P5, Day 21)

- Destination: `docs/`, `experiments/`, GitHub Release.
- Exit evidence: [acceptance and handover](06-acceptance-and-handover.md) complete; clean-clone
  reproduction recorded; report, presentation and demo prepared from actual results.

## Dependencies at a glance

```
Step 0 → Step 1 → Step 2 → Step 3 → Step 4 → Step 5 → Step 7 → Step 8
                              └────────→ Step 6 ────┘
```

## Commands (repeatable)

```bash
uv run python scripts/doctor.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python scripts/check_docs.py
uv run python scripts/validate_dataset.py data/curated.jsonl
uv run uvicorn refactor_ai.api:app --reload --host 127.0.0.1
uv run python -m evaluation.harness --output-dir experiments
```
