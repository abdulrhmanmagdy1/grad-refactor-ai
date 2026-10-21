# Clean-clone reproduction on the demonstration laptop

**Label: same-laptop clean setup.** Both attempts below ran on the demonstration laptop ([hardware record](../hardware/2026-10-20-demonstration-laptop.json)); no second physical machine was available. As the [roadmap](../../docs/planning/roadmap.md) says, this proves clean setup only, not cross-machine reproduction.

## Procedure

On 2026-10-21 the coordinator cloned `https://github.com/abdulrhmanmagdy1/grad-refactor-ai` into a new, empty folder outside the working tree and followed the [setup guide](../../docs/development/setup.md) with no files copied from the working tree:

1. `uv sync --frozen`
2. `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`, `uv run python scripts/check_docs.py`
3. `uv run python scripts/curate_dataset.py --check --download` (downloads and verifies the two pinned source files, rebuilds every curation output and compares it with the committed file)
4. In `frontend/`: `npm ci`, `npm run typecheck`, `npm test`, `npm run build`
5. A complete run in fake mode: start `uv run uvicorn refactor_ai.api:app --host 127.0.0.1` with a new, empty run database (`REFACTOR_AI_DB`), check `/health` and the interface at `/`, submit the first demonstration case in the three-role mode through `POST /api/v1/runs` and poll the run until it ends.

The fake provider is used because the model weights are not in Git ([model card](../../docs/data-and-training/model-card.md)); the run with the fine-tuned model is recorded separately in the [integration record](../integration/2026-10-21-first-real-model-run.json).

Environment: Windows 11, Python 3.11.9, uv 0.13.3, Node.js 24.12.0, npm 11.6.2, Git 2.52.0 with `core.autocrlf=true` from the system configuration, so the checkout had CRLF line endings.

## Attempt 1: commit `90462d3`

| Step | Outcome |
|---|---|
| `uv sync --frozen`, `ruff check`, `ruff format --check` | pass |
| `pytest` | 1,550 passed, 8 skipped |
| `check_docs.py` | pass |
| `curate_dataset.py --check` | **fail**: `manifest.json` and `curation-log.json` differ |
| `npm ci`, typecheck, tests, build | pass; 491 tests passed, 5 skipped |

The failure was the known defect described in the data plan at that time: the curation log hashed the raw bytes of the three external fixture files under `training/pilot/`, so the hash of `functions.py` depended on the line endings of the checkout (logged `8579d5a2…` for the CRLF bytes, `b77b9550…` for the LF bytes that Git stores). Records, metadata, the demonstration cases and the test split were identical.

Commit `74daf25` fixed it: `leakage.external_code` now hashes the content with CRLF converted to LF, a regression test checks that LF and CRLF copies of a file give the same inventory, and the curation outputs were regenerated. `records.jsonl` stayed byte for byte the same (SHA-256 `299b4f7f…`); only the logged hash of `training/pilot/functions.py` changed, together with the manifest entry that holds the log's hash and the code hash of `leakage.py`.

## Attempt 2: commit `74daf25`

| Step | Outcome |
|---|---|
| `uv sync --frozen`, `ruff check`, `ruff format --check` | pass |
| `pytest` | 1,551 passed, 8 skipped (the eight real-GPU tests) |
| `check_docs.py` | pass |
| `curate_dataset.py --check --download` | pass: "reproducible" |
| `npm ci`, typecheck, tests, build | pass; 491 tests passed, 5 skipped (the end-to-end tests that need `REFACTOR_AI_E2E_URL`) |
| `/health` | `status: ok`, `mode: fake`, provider ready |
| `GET /` | 200, the built interface |
| Run of `demo-library-fine`, three roles | `completed`, disposition `proposal_ready`: syntax pass, rubric pass, 6 of 6 reference tests passed, model review `accept`, 3 model calls |

Right after start-up `/health` reported the reference runner as still running its 19 isolation self-checks; they finished before the run reached verification, and the run executed the case's six reference tests. The interface was checked only for a 200 response here; the interface screenshots, taken with the fine-tuned model, are listed in the [report README](../../docs/report/README.md).

The console logs were kept in the coordinator's temporary directory and are not committed. GitHub Actions also passed for `74daf25` (run 39600170341: Ubuntu, Windows and frontend jobs), see the [clean-worktree record](2026-10-21-clean-worktree-verification.md#github-actions).

## Not covered

- A second physical machine, other operating systems than Windows 11 and Ubuntu (CI), and other Python versions than 3.11.
- The training environment (`.venv-train`, CUDA) and the fine-tuned model from a clean clone: the weights are not in Git, and training and evaluation ran on Kaggle through the [Kaggle lane](../../training/kaggle/README.md).
