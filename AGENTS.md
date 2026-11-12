# AGENTS.md — working in this repository

Guidance for coding agents operating in `grad-refactor-ai`. The five students retain ownership of
their workstreams; a coding agent assists but does not claim academic completion.

## Read first

1. [`README.md`](README.md) and [`docs/README.md`](docs/README.md) (documentation index).
2. [`docs/requirements/srs.md`](docs/requirements/srs.md) — FR01–FR10, NFR01–NFR07, UC01–UC04.
3. [`docs/architecture/system-design.md`](docs/architecture/system-design.md) and
   [`docs/architecture/decisions.md`](docs/architecture/decisions.md) — ADR01–ADR16.
4. [`docs/planning/roadmap.md`](docs/planning/roadmap.md) and
   [`planning/backlog.json`](planning/backlog.json) + [`planning/assignments.json`](planning/assignments.json).
5. For a single-laptop contingency workflow, read [`docs/agent-execution/`](docs/agent-execution/README.md).

## Ground rules

- **Resume from state, not memory.** Keep a checkpoint from
  [`docs/agent-execution/execution-state.template.json`](docs/agent-execution/execution-state.template.json).
- **Never invent results.** No fabricated datasets, training runs, passing tests, approvals or
  citations. If something is absent, say it is absent.
- **Respect the trust boundary (NFR01, NFR02).** The API process never executes submitted or
  generated code; inspection is AST-only. Test execution stays in `src/runner/sandbox.py`, on
  trusted examples only.
- **Distinguish implemented from planned.** The repository docs mark foundation behavior versus
  target design; keep that distinction.
- **Zero budget.** No paid APIs, hosting or storage. Keep credentials out of Git.

## Layout

```
src/api/        FastAPI app, routes, middleware, dependencies, Markdown run reports
src/core/       schemas, AST analyzer, diff utils, SQLite store, exceptions
src/agents/     analysis, refactoring, review agents + orchestrator
src/models/     BaseModelProvider, MockModelProvider, LocalModelProvider
src/runner/     isolated sandbox runner
src/evaluation/ comparison harness
src/refactor_ai backward-compatible package entry
tests/          unit, integration, sandbox, API, dataset, report/middleware/review/release tests
scripts/        doctor, check_docs, validate_dataset, generate_curated_dataset,
                prepare_blind_review, aggregate_blind_review, make_release, verify_release
training/       QLoRA training script + requirements
configs/        training configuration example
frontend/       React 19 + TypeScript + Vite + Tailwind v4 web UI (built to frontend/dist, served at /)
docs/           source documentation (see docs/README.md)
planning/       backlog.json and assignments.json
experiments/    run template, evaluation outputs, blind-review packet (experiments/review)
```

## Web client gates

```bash
cd frontend
npm ci
npm run lint        # ESLint 9 flat config (react-hooks, jsx-a11y)
npm run typecheck   # tsc --noEmit (strict)
npm run test        # Vitest
npm run build       # production bundle -> frontend/dist (served at /)
```

Every API response is validated with Zod against `src/core/schemas.py`; keep the contract in
`frontend/src/shared/api/contract.ts` in sync with the backend schemas when they change.

## Checks before finishing

```bash
uv run python scripts/doctor.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python scripts/check_docs.py
uv run python scripts/check_contract.py
uv run python scripts/validate_dataset.py data/curated.jsonl
uv run python scripts/smoke_ui.py        # needs a built frontend/dist
# After any dataset/experiments/frontend-dist change: rebuild the manifest, then verify it.
uv run python scripts/make_release.py
uv run python scripts/verify_release.py
```

`python scripts/tasks.py all` runs the same gates in that order on Windows and Linux (use it when
`uv run ruff` is unavailable, e.g. a permission error on `.venv/lib64`).

All must pass (or the failure must be reported honestly) before a change is considered done. Every
change updates the affected documentation and traces to a requirement ID. `RELEASE_MANIFEST.json`
is regenerated whenever a tracked artifact changes; never hand-edit it.

## Contract and operational invariants

- `src/core/schemas.py` is the contract source of truth; `frontend/src/shared/api/contract.ts`
  mirrors it and every response is validated by Zod (ADR17). `scripts/check_contract.py` fails on
  drift — run it after touching either side.
- Every SQLite connection applies `busy_timeout`/`synchronous` on top of WAL (ADR19); the API
  answers `429` at the concurrency cap instead of queueing unbounded background work.
- Logs are JSON lines carrying `request_id`/`status`/`duration_ms`; `/api/v1/stats` and `/metrics`
  derive from stored runs only — never estimate a number that the store cannot prove (NFR06).
