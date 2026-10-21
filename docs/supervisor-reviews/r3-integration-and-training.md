# R3 review pack: integration and first training run

Status: Prepared by the team; the meeting has not taken place; no supervisor feedback is recorded.

This pack follows the [review template](review-template.md). A coding agent drafted it on 2026-10-21 for the coordinator, Abdelrahman Magdy, from the repository records linked below. Each presenter checks their part before the meeting. Everything here is evidence and team proposals, not supervisor decisions. The meeting fields are deliberately left empty.

## Phase, date, and attendees

| Field | Value |
|---|---|
| Phase | P3 Integration and first training run (roadmap Days 6-10), tasks T12-T18 |
| Tracking Issue | [R3 #21](https://github.com/abdulrhmanmagdy1/grad-refactor-ai/issues/21) |
| Meeting date | Not held. Record the actual date. |
| Attendees | Record at the meeting. |
| Proposed presenters | Abdelrahman Magdy (run API, records and the end-to-end case), Abdullah Tarek (analysis and refactoring roles), Abdelrahman Adel (local model provider and the training run), Dania El-Walily (web interface), Shahd Abdelhay (data version and evaluation harness) |

The roadmap expects this review to show "demo, actual training status and failures" ([roadmap](../planning/roadmap.md)). Both the training status and the real-model evidence were still changing when this pack was prepared. The sections below separate committed records from work that existed only in Git-ignored folders.

## Release or code SHA and links to the demonstration and results

- Code: record the exact commit or tag shown. At preparation, local `main` was at `ee87a11` (the same commit as `origin/main` at the last fetch), and other workstreams had uncommitted changes in progress. The P3 evidence entered in local commits `d377723` (run API and SQLite history), `f282276` (role workflow, verification checks and runner), `5549a77` (web interface), `23c384b` (local model provider), `f8dc49c` (refactor-v2 and the adapter switch), `a546f84` (Kaggle lane and the root-host runner fix) and `ee87a11` (interface redesign and screenshots). No release tag existed.
- Demonstration: follow the [demonstration script](../delivery/demo-script.md) in local-model mode. Say before the first run whether the service runs the local model or the fake provider. The header shows the provider. In fake mode a permanent warning banner is shown, and every fake text starts with `FAKE PROVIDER (not a model):`.

| Evidence | What it shows |
|---|---|
| [Contracts](../architecture/contracts.md), [workflow design](../architecture/workflow.md), [workflow notes](../report/notes/workflow.md) | Analysis and refactoring roles, budgets, parsing and the run outcome (T13, T14) |
| [Backend notes](../report/notes/backend.md), [example JSON](../architecture/examples/README.md) | Run API, run states, SQLite history, recovery and the manual end-to-end checks (T15, T18) |
| [Model notes](../report/notes/model.md), [GPU provider tests](../../experiments/models/2026-10-20-local-provider-gpu-tests.json) | Local model provider in a worker process (T12) |
| [Prompt-format selection](../../experiments/models/2026-10-20-prompt-format-selection.md) | The real model on 24 validation records through the provider, refactoring role only |
| [Failed local training record](../../experiments/training/full-2026-10-20-local-attempt1-failed.json), [training configuration](../../configs/training.full.json) | First full fine-tuning attempt on the laptop (T17) |
| [Kaggle lane](../../training/kaggle/README.md) | How training and validation evaluation run on Kaggle's free GPU |
| [Validation selection rule](../../experiments/training/validation-selection-2026-10-20.json) | Base model or adapter, decided on validation only, rule written before any comparison |
| [Frontend notes](../report/notes/frontend.md), [screenshot of a ready proposal](../report/screenshots/s05-proposal-ready-light.png) | Web interface (T16); the 26 screenshots in `docs/report/screenshots/` show fake mode only |
| [Harness plumbing check](../../experiments/evaluation/2026-10-20-harness-plumbing-check.json) | Evaluation harness with the real coordinator and runner and the fake provider |

## Completed and incomplete outcomes

| Task | Planned output | State at preparation |
|---|---|---|
| T12 Local model provider | Replaceable provider with model identity and typed failures | Done. `LocalProvider` runs the pinned model in a worker process started with the training environment's interpreter. 64 core tests run without PyTorch, and the 8 real-GPU tests passed on the laptop on 2026-10-20 (the first run skipped the adapter test, and the second run passed all 8 with the pilot adapter). |
| T13 Analysis role | Structured findings | Implemented (`analysis-v1`, strict JSON parsing with one deterministic repair, static fallback). Tested with the fake provider only. |
| T14 Refactoring proposals | Bounded proposals from the provider | Implemented with the shared refactor-v2 prompt. The real model was measured on this prompt in the 24-record prompt study, which ran outside the coordinator. |
| T15 Run API and records | End-to-end run with clear errors and traceable settings | Done. Every endpoint and error code is tested, along with the bounded queue, the single worker, restart recovery and the database lock. |
| T16 Initial interface | Input, waiting and error states, explanation, diff | Done, and redesigned on 2026-10-21. The final frontend run had 488 tests passed and 5 skipped, and the build passed. There are 26 screenshots of the main states in fake mode. |
| T17 First fine-tuning experiment | Reloadable adapter, configuration, validation comparison | The local attempt failed (see below). Training moved to Kaggle in `a546f84`. At preparation the lane's Git-ignored log (`runs/kaggle/submissions.jsonl`) showed one failed and one completed training job for run id `full-2026-10-21`. Neither the training record nor the adapter checksum was committed under `experiments/training/` yet. |
| T18 Early end-to-end case | One real-model input-to-result case | Partial. Through the API: the real coordinator, the fake provider and the real runner (manual check, 2026-10-20). Through the coordinator with the real model: Kaggle smoke runs of arm A on two validation cases with `scripts/evaluate.py`. The commit message of `a546f84` states that the run after the root fix "executed and passed all reference tests (9 of 9 and 10 of 10)". Those records are Git-ignored, and an unchanged copy of the input also passes the reference tests, so this is not evidence of a successful refactoring. No run of the service in local-model mode through the web interface is recorded. |

Measured facts to present, all from committed records:

- **Provider.** Model load took 17.6 s with a warm file cache and 88.1 s cold. The model process used about 1.0 GB of GPU memory. Decoding ran at 13.8 to 26.1 tokens per second (median 24.5). Greedy decoding was verified, and outputs were byte-identical across runs. A per-call timeout stops the worker, and the next call starts a new one.
- **Real model, refactoring role, refactor-v2, 24 validation records.** 24 of 24 outputs parsed, 5 passed the rubric, 19 passed the reference tests and 2 passed every check. 14 outputs were unchanged copies of the input. Median latency was 5.09 s and the maximum 10.60 s per call.
- **Local training attempt (2026-10-20).** Configuration: rank 8, alpha 16, `max_length` 1,024 with gradient checkpointing, 3 epochs, effective batch 8. The run stopped after 22 of 237 planned steps (179.5 s) with `CUBLAS_STATUS_EXECUTION_FAILED` in the backward pass. Windows logged low virtual memory, with the training process the largest consumer at 7.6 GB. At the start of the run about 775 MB of RAM was available while other workstreams were running. The logged training loss fell from 0.740 (step 1) to 0.102 (step 20). No checkpoint was saved. All 711 train and validation records fit 1,024 tokens (maximum 695).
- **Kaggle lane.** It uses a private dataset holding a deterministic code bundle, private GPU kernels on a Tesla T4 with pinned packages, a SHA-256 check of the model weights, and per-file hash checks when outputs are fetched. The T4 has no native bf16, so it trains and runs inference in fp32, while the laptop uses bf16. Every run manifest records the precision. The kernel fixes the split to `validation`.
- **Selection rule (T22).** The rule was written at 2026-10-20T12:47:17Z, before any comparison. Adopt the adapter for the refactoring role if arm C's `proposal_ready` count on all 84 validation cases is higher than arm A's. Otherwise keep the base model and report that result.

## Problems and alternatives

1. **No real-model run through the service and the interface is recorded.** The roadmap gate is "Demonstrate a real model by Day 10". Alternatives: rehearse the [demonstration script](../delivery/demo-script.md) in local-model mode and keep the run ids and screenshots, or accept the Kaggle smoke runs, which use the real coordinator but not the service.
2. **Training could not run on the laptop under the shared load.** The 4 GB GPU spills into system RAM on Windows, and the laptop had 7.8 GB of RAM shared with five workstreams. Training and the validation evaluation therefore moved to Kaggle's free GPU, which brings these consequences:
   - The hardware and precision differ (T4 in fp32 against the RTX 2050 in bf16), so results computed on Kaggle can differ slightly from inference on the laptop.
   - The work now depends on an external free service with session limits and quotas, which the [risk list](../planning/risks.md) names as "interrupted free compute".
   - It departs from ADR04, local operation ([decision log](../architecture/decisions.md)).

   Alternatives: train on the laptop with nothing else running (not tried); obtain university GPU time (not available so far); use a smaller `max_length` (not needed, because all records fit 1,024 tokens).
3. **Project data on a third-party platform.** The bundle includes the dataset file with all 799 records. That covers the frozen test records and the 795 team-authored records whose license is still pending ([R2](r2-data-and-baseline.md), question 1). The data sits in a private Kaggle dataset under a team member's account. No model is trained or evaluated on the test split there: the kernel fixes the split to `validation`, and the training script never passes test records to the trainer.
4. **The new results were not committed.** The training record, the adapter checksum and the validation evaluation records existed only in Git-ignored `runs/` folders. The [model card](../data-and-training/model-card.md) still said "not trained". Owner: the models workstream (records, model card), with the data workstream for the evaluation records.
5. **The roles have not been measured with the real model.** The analysis and review roles were tested with the fake provider only. One 0.5B model serves as analyst, refactorer and reviewer. Olausson et al. (2024) report that self-repair is limited by the quality of the feedback ([related work](../research/related-work.md), R8), so weak reviews are expected.
6. **The validation evaluation runs with the draft protocol's limits** (768 new tokens for refactoring, 2,048 input tokens for every role). The service uses 1,024 for refactoring and 4,096 input tokens for review ([R2](r2-data-and-baseline.md), problem 4). In the prompt study the longest refactor-v2 output was 211 tokens, so the refactoring limit was not binding there.

## Questions requiring a decision

1. **Compute outside the laptop.** Team proposal: accept Kaggle's free GPU (private dataset, private kernels) for training and validation evaluation, record the hardware and precision in every manifest, and keep demonstration inference on the laptop. Ask whether this is acceptable, given ADR04 and the roadmap's wording ("obtain confirmed free university GPU access").
2. **Hardware for the final test evaluation.** Options: (a) Kaggle T4 in fp32, the same hardware as the validation selection; (b) the laptop in bf16, the same hardware as the demonstration. No team proposal is recorded yet. The choice must be written into the protocol freeze record.
3. **Project data on Kaggle.** Ask whether keeping the team-authored data and the frozen test records in a private Kaggle dataset is acceptable under the university's rules. This is linked to the license question in R2.
4. **Evidence for the real-model end-to-end case.** Ask what the supervisor accepts for the Day 10 gate: a recorded local-model run through the service and the interface, or the Kaggle smoke runs through the coordinator.
5. **Fine-tuning deliverable.** Team proposal: the deliverable is met by a committed training record (configuration, data hash, code SHA, hardware, duration, losses), the adapter checksum, and the validation comparison under the pre-written rule, whatever its outcome. Ask whether a plain count comparison without a significance test is acceptable for the selection, given 84 validation cases from 12 families.
6. **Generation limits.** This is R2 question 7 again, now concrete. Should the validation evaluation be repeated after the protocol's limits are reconciled with the service, or kept, with the difference recorded?

## Supervisor feedback

Empty until the meeting. Record what the supervisor said, separately from the team's proposals above.

- Question 1, compute outside the laptop:
- Question 2, hardware for the test evaluation:
- Question 3, project data on Kaggle:
- Question 4, real-model end-to-end evidence:
- Question 5, fine-tuning deliverable:
- Question 6, generation limits:
- Demonstration shown (commit, mode, cases, outcomes):
- Other feedback:

## Agreed and pending decisions

| Question | Team proposal | Decision recorded at the meeting | Status |
|---|---|---|---|
| 1 Compute outside the laptop | Kaggle for training and validation evaluation; local inference for the demonstration | | Pending |
| 2 Hardware for the test evaluation | No proposal; options (a) and (b) | | Pending |
| 3 Project data on Kaggle | Private dataset only; follow the university rules | | Pending |
| 4 Real-model end-to-end evidence | A recorded local-model run through the service | | Pending |
| 5 Fine-tuning deliverable | Record, checksum and validation comparison under the pre-written rule | | Pending |
| 6 Generation limits | Reconcile before the protocol freeze | | Pending |

## Follow-up Issues, owners

Proposed follow-ups. Create them as Issues only after the meeting.

| Follow-up | Owner |
|---|---|
| Commit the Kaggle training record, the adapter checksum and the lane's job record; update the model card | Abdelrahman Adel |
| Commit the validation evaluation records and report them with the protocol's tables; apply the selection rule and record the decision (T22) | Shahd Abdelhay (records, tables), Abdelrahman Adel (decision) |
| Rehearse the demonstration in local-model mode, keep the run ids and capture local-model screenshots | Dania El-Walily, with Abdelrahman Magdy |
| Record the compute and data-location decisions in the decision log (a new ADR or an ADR04 amendment) | Abdelrahman Magdy |
| Measure the analysis and review roles with the real model from the validation records (parse failures, fallbacks, verdicts) | Abdullah Tarek |

## Conditions for moving to the next phase

- The training record and the adapter checksum are committed, or the training blocker is recorded with the supervisor.
- A real-model run through the service exists with its run record, or the supervisor accepts other evidence (question 4).
- The compute and data-location decisions (questions 1 to 3) are recorded before the test split is evaluated anywhere.
