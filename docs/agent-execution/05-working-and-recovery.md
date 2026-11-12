# 05 — Working and recovery

Single-laptop setup, Git workflow, state, restart and blocker handling.

## Setup

```bash
git clone https://github.com/abdulrhmanmagdy1/grad-refactor-ai.git
cd grad-refactor-ai
uv sync --frozen
uv run python scripts/doctor.py
uv run pytest
```

The base environment runs on CPU and does not download a model. Training uses a separate,
hardware-matched environment (see the [training plan](../data-and-training/training-plan.md)).
Never paste credentials into a prompt or commit them; keep `.env`, `data/`, `models/`, `runs/`
and `.venv/` out of Git.

## Git workflow

```bash
git switch main
git pull --ff-only
git switch -c feat/123-short-description
# focused change + checks + docs
# open a linked PR using "Closes #123"
```

- Do not force-push `main`; a second-person approval is not required (the task owner checks and
  merges when ready).
- Record blockers and needed help in the Issue. Uploading a file alone is not completion.
- Training work includes versions, settings, artifacts and actual results.

## State and checkpoints

- Copy `execution-state.template.json` to a working file before starting and update it after each
  step. **Resume from state, not memory.**
- Keep evidence links (command output, files, hashes) next to each step in the state file.
- Use `--resume-from-checkpoint` for training; save checkpoints within the storage quota.

## Restart procedure

1. Read the state file and the current `git status` / recent commits.
2. Re-run `uv run pytest` and `uv run python scripts/doctor.py` to confirm the baseline.
3. Continue from the first incomplete step in
   [`02-execution-plan.md`](02-execution-plan.md); do not redo verified steps.

## Blocker handling

Record the blocker with: what was attempted, the exact error, the affected step, the proposed
reduced-scope alternative, and the decision needed. Blocked items stay visible rather than being
silently dropped. The hardware gate in particular may end in a **recorded blocker** instead of a
training run; that is an acceptable, honest outcome.

## Boundaries

- The API must not execute submitted code. Enable a separate runner only after its isolation
  checks pass on trusted examples.
- Do not commit credentials, private contact details, unlicensed data or large model weights.
- Do not mark a supervisor review approved before it happens.
