# Development environment

The core environment runs on CPU and does not download a model. Training uses a separate environment matched to the available GPU. Keep credentials and local data outside Git.

## Requirements

Install Git, Python 3.11, and [uv](https://docs.astral.sh/uv/getting-started/installation/) from their official sources. Repository access is required. Node.js will be needed when the product interface is implemented; there is no frontend application in this foundation.

## Setup

```bash
git clone https://github.com/abdulrhmanmagdy1/grad-refactor-ai.git
cd grad-refactor-ai
uv sync --frozen
uv run python scripts/doctor.py
uv run pytest
uv run uvicorn refactor_ai.api:app --reload --host 127.0.0.1
```

These uv commands also work in Windows PowerShell without activating the virtual environment manually. Open http://127.0.0.1:8000/docs and try POST /api/v1/analyze. The service parses code but does not execute it.

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
