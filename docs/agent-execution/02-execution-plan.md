# Ordered execution plan

Steps are ordered for one coding agent on one laptop. Human workstreams can prepare independently, but all consumers use the same contracts. Track the mapped Issues; completion requires their acceptance criteria, not only these short descriptions. Supervisor gates remain real meetings, not automated approvals.

## Step 0 - Inspect and reproduce the foundation (T01, T02; Day 1)

Read Git status/log and existing AGENTS.md instructions. Preserve local changes. Run uv sync --frozen, uv run python scripts/doctor.py, uv run pytest, uv run ruff check ., uv run ruff format --check . and uv run python scripts/check_docs.py. Read scripts before invocation if the checkout has changed. Start the existing API using the setup guide and confirm /health and /api/v1/analyze. Record sanitized hardware, versions, check outcomes and existing deficiencies in experiments/. Copy the execution-state template to execution-state.json and fill actual values.

Exit: reproducible foundation or precise setup blocker. Do not delete or replace this repository to start again.

## Step 1 - Feasibility and narrow scope (T03-T06, R1; Days 1-2)

Review primary references and candidate dataset/model licenses. Pin a model revision and measure a few inference cases on this laptop. Specify one supported transformation and its exclusions with input/output examples. Inspect and repair training scaffolding; create a separate hardware-compatible training environment. Run a tiny LoRA experiment using licensed pilot fixtures, then save, reload and generate with the adapter. This pilot is not a final experiment and cannot touch the held-out test split.

Write hardware and model evidence, scope decision and measured resource bounds. If training is impossible, record the shortfall and confirmed free alternative if available. Prepare R1 evidence; keep meeting feedback pending until received. See 04-data-model-evaluation.md for the hardware gate.

Exit: an evidence-based model/task decision, training status and R1 record or explicit pending decision.

## Step 2 - Data, baseline and contracts (T07-T11, R2; Days 3-5)

Implement a curation command using the schema in the existing data plan. Record source/license and exclusions; split by source_group; detect exact and near duplicates across splits. Save stable manifests and hashes. Freeze the test split before model/prompt selection. Implement base-model single-role inference with fixed generation settings and retained failures. Measure on development/validation cases and freeze the comparison protocol and targets.

Create Pydantic role/run schemas and example API responses following 03-component-contracts.md. Record the SQLite/queue/UI choices in the architecture decisions. Implement contract tests before connecting UI. Prepare R2 evidence and note any pending decision.

Exit: repeatable data commands, split manifest, baseline records, fixed protocol and tested contracts.

## Step 3 - First vertical slice (T12-T18, R3; Days 6-10)

Implement src/refactor_ai/providers/ with the same bounded interface for base and adapter models and an explicit fake provider for tests. Implement roles and a coordinator under src/refactor_ai/agents/. Extend the API with queued run submission, polling and local history; preserve existing endpoints or document migration. Serialize model inference and keep heavy work outside request handlers. Add SQLite persistence and bounded startup recovery.

Build frontend/ with input, submit, progress, error, diff, explanation and download states. Pin and lock its dependencies; connect to the same backend contracts with a documented local URL/CORS policy. Train a small real adapter only after the hardware and data gates; record command/config, loss, runtime, memory and artifact hashes. Compare adapter to base on validation data.

Demonstrate one actual model run from browser input to result by Day 10. Keep fake-provider demos clearly labeled. Record the real state of verification features. Update setup commands and prepare R3 evidence.

Exit: real-model vertical slice plus training evidence or a visible blocked fine-tuning objective. Do not let training prevent independent UI/API completion.

## Step 4 - Verification and feature freeze (T19-T23, R4; Days 11-15)

Complete the analysis/refactor/review sequence with at most one correction. Separate model verdict from static checks and trusted reference tests. Implement the runner outside the API with the controls and failure cases in the testing guide. Disable execution if isolation prerequisites are missing; return not_run with the reason. This is a visible release limitation, not a pass.

Handle malformed JSON, invalid syntax, unsupported tasks, excessive input, model load errors, queue saturation, timeouts, missing tests and failed checks. Keep original input intact. Finish verification display and downloads. Select the model using validation only; retaining the base model is permitted when justified, but report adaptation findings. Execute a requirements-to-test matrix and freeze features/model choice at R4.

Exit: acceptance evidence, frozen configuration, known defects and R4 record or pending feedback.

## Step 5 - Final evaluation and delivery (T24-T28, R5; Days 16-21)

Run the frozen A/B/C/D protocol on the test split. Keep all attempts, errors and timeouts, model settings, budgets and case IDs. If an arm is infeasible mark it not_run with a reason; do not invent comparisons. Generate tables/figures from raw records and state the limits of the sample.

Reproduce installation from a clean clone and fresh environment. Use a second physical machine if available; otherwise label the evidence same-laptop clean setup. Fix critical defects without tuning on the test set. Assemble the report from implementation and real experiments, update user/developer guides and model card, prepare slides, demo cases and a backup recording. Rebuild the two PDF documents if their sources changed, inspect their rendered pages and refresh the manifest.

Complete 06-acceptance-and-handover.md. Prepare tag/release notes and artifact references within repository quotas; publish only if the current session authorizes remote publication. Prepare R5; record real feedback when received. Stop adding features during final delivery.

Exit: reproducible release candidate with explicit incomplete items, evidence index and human handover. A blocker means partial delivery, never automatic success.
