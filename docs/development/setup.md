# Development environment

The core environment runs on CPU and does not download a model. Training uses a separate environment matched to the available GPU. Keep credentials and local data outside Git.

## Requirements

Install Git, Python 3.11, and [uv](https://docs.astral.sh/uv/getting-started/installation/) from their official sources. Repository access is required. To build the web interface in `frontend/`, also install Node.js 24.12.0 or a newer 24.x release with npm 11.6 or newer (the versions `frontend/package.json` requires).

## Setup

```bash
git clone https://github.com/abdulrhmanmagdy1/grad-refactor-ai.git
cd grad-refactor-ai
uv sync --frozen
uv run python scripts/doctor.py
uv run pytest

cd frontend
npm ci
npm run build
cd ..

uv run uvicorn refactor_ai.api:app --reload --host 127.0.0.1
```

These uv commands also work in Windows PowerShell without activating the virtual environment manually. Open http://127.0.0.1:8000/docs for the API reference, then try POST /api/v1/analyze or submit a run as described below. The service parses code but never executes it.

## Running the service

```bash
uv run uvicorn refactor_ai.api:app --host 127.0.0.1 --port 8000
```

Start it from the repository root, because relative paths in the settings are resolved against the working directory. With `--reload`, a code change restarts the process: the run in progress gets up to 10 seconds to finish and is otherwise recorded as interrupted, and runs still waiting are recorded as interrupted. Only one service process can use a run database: a second start with the same REFACTOR_AI_DB (for example in another terminal) stops at startup with "The run database ... is already in use by another service process" and leaves the running service's runs untouched. The lock is held on a file next to the database with `.lock` appended to its name (by default `runs/app/runs.sqlite3.lock`).

**Fake mode (default).** The deterministic fake provider stands in for the model and labels every text `FAKE PROVIDER (not a model):`. GET /health reports `"mode": "fake"`. Use it for development and tests; its output is never evidence of model behavior.

**Local model mode.** Create `configs/model.local.json` (ignored by Git) from the models workstream's `configs/model.example.json`; the keys are documented in `src/refactor_ai/providers/local.py`. Then start the service with the provider variable set:

```powershell
$env:REFACTOR_AI_PROVIDER = "local"
uv run uvicorn refactor_ai.api:app --host 127.0.0.1 --port 8000
```

On Linux or macOS use `REFACTOR_AI_PROVIDER=local uv run uvicorn refactor_ai.api:app --host 127.0.0.1 --port 8000`. The service starts at once and loads the model in the background. While it loads, GET /health reports `"mode": "local_model"`, the configured model identity, `"ready": false` and "The model is loading in the background since startup; runs wait until it is ready."; submitted runs stay `queued` until the load finishes. If loading fails, /health shows the provider's reason and runs fail with it.

**Fine-tuned adapter.** Set `REFACTOR_AI_REFACTOR_USE_ADAPTER=true` to run the refactoring role with the LoRA adapter configured in `configs/model.local.json` (the analysis and review roles always use the base model). GET /health then reports `"refactor_use_adapter": true`. If the provider has no adapter configured, /health says so in the provider detail with `"ready": false`, and every run fails with error code `adapter_unavailable` before any model call; the base model is never used in its place.

| Variable | Default | Meaning |
|---|---|---|
| REFACTOR_AI_PROVIDER | `fake` | `fake` or `local` |
| REFACTOR_AI_MODEL_CONFIG | `configs/model.local.json` | Local model, adapter and worker interpreter settings |
| REFACTOR_AI_DB | `runs/app/runs.sqlite3` | SQLite run history, ignored by Git |
| REFACTOR_AI_RUNNER | `auto` | `auto` runs trusted reference tests only when the runner's isolation checks pass; `disabled` always reports `not_run` |
| REFACTOR_AI_MAX_PENDING | `4` | Unfinished runs allowed at once (waiting plus running), 1 to 100 |
| REFACTOR_AI_RETENTION | `200` | Stored runs kept, 1 to 100,000; the oldest finished runs are deleted first |
| REFACTOR_AI_REFACTOR_USE_ADAPTER | `false` | `true` runs the refactoring role with the configured LoRA adapter; accepts `true`/`false`, `1`/`0`, `yes`/`no`, `on`/`off` |
| REFACTOR_AI_PROJECT_MODEL_CONFIG | `configs/model.project.local.json` | The GGUF model of the project review mode; used with `REFACTOR_AI_PROVIDER=local` when the file exists, otherwise project reviews use the static checks only |
| REFACTOR_AI_PROJECT_TESTS | `false` | `true` lets a project review run the uploaded project's own tests when the person asks for it; off by default because those tests execute the uploaded code on this machine |

An invalid value stops startup with a message that names the variable; an empty value means the default.

**Using the run API.** POST /api/v1/runs with `{"code": "...", "workflow_mode": "multi_role"}` returns 202 with a `run_id`; poll GET /api/v1/runs/{run_id} until `status` is `completed` or `failed`, then read the diff and the verification results, download GET /api/v1/runs/{run_id}/proposal and record a decision with POST /api/v1/runs/{run_id}/decision. GET /api/v1/reference-cases lists the demonstration cases whose trusted tests can run. The [contracts](../architecture/contracts.md), the [example JSON](../architecture/examples/README.md) and the [backend notes](../report/notes/backend.md) describe every field and error.

**Web interface.** When `frontend/dist` exists, the same process serves the built interface at http://127.0.0.1:8000/. A fresh clone has no `frontend/dist` (Git ignores it), so run `npm ci` and `npm run build` in `frontend/` first; without the build, GET / answers the JSON 404 `not_found`. The [frontend guide](frontend.md) covers frontend development. During frontend development the API accepts browser requests only from `http://127.0.0.1:5173` and `http://localhost:5173`.

**Run history.** Delete one run with DELETE /api/v1/runs/{run_id}. To clear everything, stop the service and delete `runs/app/`, or point REFACTOR_AI_DB at another file.

**Contract examples.** After changing a contract model, the task module or an error message, regenerate the examples with `uv run python scripts/export_contract_examples.py`; `--check` verifies them, and the test suite fails while they are stale.

## Before a pull request

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run python scripts/check_docs.py
```

## Training environment

Follow the training plan after confirming the GPU and VRAM. Select a compatible PyTorch and CUDA build for the actual machine. Do not install a CUDA configuration on a Mac or CPU-only machine by assumption.

training/requirements.in lists candidate dependencies. Pin a separate training environment after the GPU smoke test. The core uv.lock does not reproduce the GPU training environment.

## Local files

data/, models/, runs/, .env, and .venv/ are excluded from Git. Commit sanitized experiment records under experiments/. Distributable artifacts may use GitHub Releases after size and licensing checks. Record the base-model identifier and revision rather than committing another copy of its weights.

## Troubleshooting

For access errors, check the account and invitation status. For Python version errors, install 3.11 or use uv's Python management. For training memory errors, reduce context, batch size, or model size and change one factor at a time. Keep paid services outside the agreed plan.
