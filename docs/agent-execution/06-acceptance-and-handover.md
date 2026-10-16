# Acceptance evidence and human handover

Check these against the requirements and Issue acceptance criteria. A checkbox is checked only after evidence exists. The implementation agent produces the evidence; students inspect and accept their own workstream. There is no assigned peer-review chain.

## Implementation evidence

- [ ] Clean setup from documented commands, pinned core environment and frontend/training locks where applicable.
- [ ] Foundation API still works or has a documented migration; health indicates actual operating mode.
- [ ] One supported Python transformation with explicit exclusions, valid examples and reference tests.
- [ ] Real local model run with pinned model/license, measured limits and typed failures.
- [ ] Analysis, refactoring and review roles with strict schemas and bounded calls/correction.
- [ ] Run submission, polling, persistence, interruption recovery and queue saturation checks.
- [ ] UI input/progress/error/diff/explanation/download behavior, preserved original input and clear model mode.
- [ ] Syntax, model review and reference-test status displayed independently; missing tests never count as pass.
- [ ] Runner isolation/cleanup checks before trusted-fixture execution; missing prerequisites clearly disable it.
- [ ] Relevant backend, frontend and integration checks pass; CI does not download a model or require a GPU.

## Research evidence

- [ ] Licensed source records and source-separated split manifest with duplication checks.
- [ ] Tiny real training smoke test, adapter save/reload, hardware and dependency evidence.
- [ ] Real fine-tuning record and artifact checksums, or an explicit unmet requirement and blocker.
- [ ] Validation-only selection and frozen final test protocol.
- [ ] A/B/C/D records including failures or explicit infeasible arms, with counts and budgets.
- [ ] Reproducible plots/tables and honest model card, limitations and negative findings.

## Delivery evidence

- [ ] Clean-clone reproduction, labeled same-laptop or second-machine according to actual evidence.
- [ ] English report, user/developer guides and PDFs agree with actual implementation.
- [ ] Stable success, unsupported-input and failed-check demonstration cases plus backup recording.
- [ ] Release candidate/tag plan, artifact retrieval instructions, licensing and checksums.
- [ ] Five supervisor review records distinguish prepared, pending and actual feedback.
- [ ] execution-state.json and an evidence index show implemented/tested/blocked/pending work.

## Handover file

Create docs/delivery/implementation-handover.md with: exact commit and branch; commands to install/start/test/train/evaluate; actual hardware and environment versions; component map; chosen task and input limits; model/adapter/data references; results and denominators; known defects; blocked requirements; supervisor decisions still pending; and next steps. Link every substantive claim to retained evidence. Do not create a final release claim if critical requirements remain unmet.

## Team inspection by workstream

| Member | What they inspect and should be able to explain |
|---|---|
| Abdelrahman Magdy | Setup, API, storage, integration, recovery and release commands |
| Abdullah Tarek | Role contracts, coordination, correction limit, verification and failure tests |
| Abdelrahman Adel | Model choice, actual fine-tuning, adapter reload, versions and resource measurements |
| Shahd Abdelhay | Provenance, split/leakage evidence, protocol, metrics, denominators and limitations |
| Dania El-Walily | UI states, diff/download, report consistency, slides and repeatable demonstration |

Human inspection happens after implementation and before accepting the delivery. An agent cannot fabricate those inspections or substitute for students understanding the system.
