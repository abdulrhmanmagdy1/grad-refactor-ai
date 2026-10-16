# Single-laptop working and recovery

## Initial setup

Use the private repository's normal authenticated clone flow. On an existing clone, inspect git status and git log, then fetch. Pull with --ff-only only when the working tree is clean and the current branch is intended. If histories diverge or local work exists, preserve it and resolve deliberately; do not reset --hard, force-push or overwrite changes. Never put a token in a command line or prompt.

Use Python 3.11 and uv sync --frozen for the current core environment. Run the commands in docs/development/setup.md. Frontend and training environments are introduced only when their steps begin, each with a version/lock and startup instructions. Record the laptop OS. Avoid running training and inference concurrently on constrained hardware. CI remains GPU independent.

## Per-step loop

1. Read the step, mapped Issues and actual dependency evidence.
2. Implement one coherent change using the existing layout and shared contracts.
3. Run relevant checks and record the exact command, timestamp, code version, exit status and artifact references. Do not dump credentials or private inputs.
4. Update affected guides, experiment notes and execution-state.json.
5. Commit a focused change if authorized. Update GitHub Issues only if the current session authorizes remote project changes. No teammate approval is required by this plan.

The coding tool can implement all workstreams sequentially on one laptop; Issue ownership still identifies the student responsible for understanding and validating that area. Never claim to be that student or to have met the supervisor. The team handles communications and academic submission.

## Checkpoints and resume

Copy execution-state.template.json to execution-state.json when starting. Record status as not_started, in_progress, completed, blocked or pending_human. For each completed step retain evidence and exit checks. Include last known commit, environment references, active branch, next action and blockers. Keep tokens, personal emails and full private inputs out of this tracked file.

On resume, read this state, then verify its claims against Git and actual artifacts. A stale state is a hint, not authority. Re-run only checks invalidated by new changes or missing evidence. Resume the first incomplete dependency-ready step. An interrupted training run needs an existing validated checkpoint and matching config/data; otherwise restart with a new run ID and retain the failed record.

## Blockers and human gates

Missing GPU, data rights, model access, insufficient disk, unsupported platform, rejected isolation checks or required supervisor decisions are real blockers. Record what failed, evidence, impact, options and the specific human action needed. Continue independent steps using clearly named test fixtures or a fake provider where appropriate. Keep actual-model, training, reference-runner and final-evaluation tasks open when unmet.

Prepare supervisor review materials at Days 2, 5, 10, 15 and 21. Store summaries as prepared/pending until the human supplies feedback. Do not infer approval from silence. Final human inspection is required before the team claims an accepted deliverable; independent coding does not need repeated confirmation of routine reversible implementation choices.

## Reproducibility and storage

Keep downloads in ignored directories. Document required disk and exact download revisions; do not move huge weights into Git history. Save sanitized small evidence under experiments/. Define cleanup and user-input retention without deleting needed experimental records. For a clean install test, use another directory and fresh environment; same-laptop evidence must not be described as second-machine validation.
