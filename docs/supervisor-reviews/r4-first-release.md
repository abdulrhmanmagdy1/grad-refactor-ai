# R4 review pack: integrated first release

Status: Prepared by the team; the meeting has not taken place; no supervisor feedback is recorded.

This pack follows the [review template](review-template.md). A coding agent drafted it on 2026-10-21 for the coordinator, Abdelrahman Magdy, from the repository records linked below. Each presenter checks their part before the meeting. Everything here is evidence and team proposals, not supervisor decisions. The meeting fields are deliberately left empty. The roadmap's purpose for R4 is "readiness for final evaluation": the feature freeze, the model choice and the frozen protocol must be settled before the test split is run.

## Phase, date, and attendees

| Field | Value |
|---|---|
| Phase | P4 First-release integration (roadmap Days 11-15), tasks T19-T23 |
| Tracking Issue | [R4 #27](https://github.com/abdulrhmanmagdy1/grad-refactor-ai/issues/27) |
| Meeting date | Not held. Record the actual date. |
| Attendees | Record at the meeting. |
| Proposed presenters | Abdullah Tarek (review, coordination, runner, acceptance), Abdelrahman Magdy (integration and failure handling), Abdelrahman Adel (model selection), Shahd Abdelhay (harness dry run and protocol freeze), Dania El-Walily (result presentation and report draft) |

## Release or code SHA and links to the demonstration and results

- Code: record the exact commit shown. It must be a commit, not a working tree. At preparation, local `main` was at `ee87a11`, and the backend, workflow and evaluation workstreams had uncommitted changes to 35 files. These covered parsing, the runner's handling of the run deadline, harness resume, and new tests. No release tag existed.
- Demonstration: run the [demonstration script](../delivery/demo-script.md) in the configuration chosen at T22 (base model or adapter for the refactoring role). Show the three required outcomes: a success, an unsupported input, and a failed or rejected check.

| Evidence | What it shows |
|---|---|
| [Workflow design](../architecture/workflow.md), [workflow notes](../report/notes/workflow.md) | Review role, single correction, budgets, deadline, adapter integrity, disposition order (T19) |
| [Runner safety](../development/runner-safety.md) | The isolated reference runner, its 19 self-checks and its honest limits (T20) |
| [Backend notes](../report/notes/backend.md), [frontend notes](../report/notes/frontend.md) | Verification and failure results in the API and the interface (T21) |
| [Screenshots](../report/screenshots/s05b-diff-and-verification-light.png) | Diff and the four verification results; all screenshots show fake mode |
| [Validation selection rule](../../experiments/training/validation-selection-2026-10-20.json), [model card](../data-and-training/model-card.md) | Model selection (T22) |
| [Evaluation protocol (draft)](../evaluation/protocol.md), [harness plumbing check](../../experiments/evaluation/2026-10-20-harness-plumbing-check.json) | Harness dry run and the freeze procedure |
| [Requirements](../requirements/srs.md), [acceptance and handover](../agent-execution/06-acceptance-and-handover.md) | What the acceptance matrix (T23) must trace |
| [Acceptance matrix (draft)](../delivery/acceptance-matrix.md), [acceptance status (draft)](../delivery/acceptance-status.md) | The T23 working drafts of 2026-10-21: the requirement trace with a test snapshot, and a walk through both acceptance checklists. Pending Abdullah Tarek's inspection |
| [User guide](../delivery/user-guide.md) | How the release is used |

## Completed and incomplete outcomes

| Task | Planned output | State at preparation |
|---|---|---|
| T19 Review and coordination | Review step, bounded correction, coordination | Done. Prompts `review-v1` and `correction-v2`. Exactly 1 call in single-role runs, at most 5 calls and 1 correction in multi-role runs. A run deadline is checked before every step. A run fails when the provider reports another adapter state than the one requested. The disposition order is checked over all 450 combinations of the four dimensions and both modes. All of this was tested with the fake provider. |
| T20 Separate runner for trusted examples | Isolated runner with checks | Done. All 19 isolation self-checks passed on the Windows laptop, and the six demonstration cases' original and reference code passed their 52 tests in it. Linux: `tests/test_runner.py` and `tests/test_runner_child.py` passed in the Ubuntu CI job as a non-root user (GitHub Actions run 39418314923, commit `5549a77`). `a546f84` added the root-host case: the test process runs as user and group 65534. |
| T21 Verification and failures in the interface | Honest status display | Done. The four results are shown separately; missing evidence is drawn as absent and never as a pass. The failed-run view shows the error code, the stage and "Try again". Contract mirror and example tests cover every run error and stop reason. Screenshots S10, S11, S15 and S16 (busy, interrupted, model loading and missing adapter, `adapter_unavailable`) were not captured. |
| T22 Model selection on validation data | Selected model, evidence, model card | Pending. The rule was written before any comparison. At preparation a validation evaluation of arms A to D on the 84 validation cases was running on Kaggle, according to the lane's Git-ignored log. No result or decision was recorded. The model card still said "Status: not trained" and named refactor-v1. |
| Harness dry run (data and evaluation) | Process ready for the frozen test set | Done with the fake provider: 24 attempts on 6 validation cases, every attempt recorded, budgets matched the arms, and both test-split refusals were checked. The real-model dry run is the Kaggle validation evaluation above. |
| T23 First-release acceptance | Acceptance evidence | In progress. Working drafts of the [acceptance matrix](../delivery/acceptance-matrix.md) and the [acceptance status](../delivery/acceptance-status.md) appeared on 2026-10-21, uncommitted and pending the owner's inspection. Their test snapshot ran at `ee87a11` with uncommitted changes, file group by file group: 1,493 passed, 8 skipped, 0 failed in 27 files. `docs/delivery/implementation-handover.md` did not exist. |
| Feature freeze | Declared at the end of P4 | Not declared. |

Requirements status to discuss, summarized from the draft [acceptance matrix](../delivery/acceptance-matrix.md). The draft has not been inspected by its owner; refresh this table from the inspected matrix before the meeting.

| Status in the draft matrix | Requirements | Open point |
|---|---|---|
| Implemented and tested | FR01, FR02, FR04-FR08, FR10, NFR01, NFR03, NFR04, NFR06 | Tests use the fake or scripted providers for model behavior. FR08's limits differ between the service and the draft protocol ([R2](r2-data-and-baseline.md), problem 4) |
| Implemented, evidence pending | FR03, FR09, NFR05 | No committed record shows the real model's proposals through the workflow, the A/B/C/D comparison, or the final training and evaluation records |
| Partially implemented | NFR02, NFR07 | NFR02: no operating-system privilege, network or file-system boundary (problem 2). NFR07: measurements exist ([model records](../../experiments/models/README.md)), but no targets |

## Problems and alternatives

1. **The feature freeze has not happened while changes continue.** Alternatives: freeze at the commit shown in the meeting, and accept only defect fixes with a linked Issue after that; or move the freeze and record the slip.
2. **The runner is a hardening layer, not a sandbox.** The test process runs as the same user as the service on Windows. Network and file-system access are refused by the audit hook, not by the operating system. There is no administrator account and no Docker on the laptop. This is acceptable only because the runner executes model proposals for server-owned demonstration cases ([runner safety](../development/runner-safety.md)). Alternatives (future work): a restricted token or AppContainer on Windows; user and network namespaces or a rootless container on Linux.
3. **Pasted code can never reach `proposal_ready`.** Trusted reference tests exist only for the six demonstration cases, so a function the user pastes ends at best as `uncertain` (`tests_not_available`). This is deliberate: missing tests never count as a pass, and model-generated tests are excluded from the [task scope](../requirements/task-scope.md).
4. **Documents describe older states.** At preparation:
   - The [system design](../architecture/system-design.md) still said that the interface, model provider, agents, run history and test runner were not implemented.
   - ADR13 and the model card named refactor-v1.
   - The README status (dated 2026-10-20) said that the runner's Linux path had not been executed.
   - The execution state (`docs/agent-execution/execution-state.json`) was last verified at `3aa2998`.
   - The user guide described the verification results as four cards, while the redesigned interface shows them as one list of four entries.

   The draft acceptance matrix lists further cases, including the [testing page](../development/testing.md) and the planning edition of the PDFs. Owners: the coordinator (system design, ADR13, README, execution state, PDFs), the models workstream (model card), the workflow and verification workstream (testing page) and the delivery workstream (user guide).
5. **The protocol is not frozen and no targets exist.** The freeze record must follow the validation baseline and precede any test run. The generation limits and the hardware of the test evaluation are open ([R3](r3-integration-and-training.md), questions 2 and 6).
6. **The screenshots are fake mode only.** No screenshot shows the local model, a `rejected` or `failed` outcome, or the missing-adapter state.

## Questions requiring a decision

1. **Feature freeze.** Team proposal: freeze the behavior described in the [contracts](../architecture/contracts.md) and the [user guide](../delivery/user-guide.md) at the commit shown, with one task, one function per run, single-role and multi-role workflows, the four verification dimensions, history, download and decisions. After the freeze, only defect fixes are made. Ask the supervisor to confirm.
2. **Runner safety level.** Ask whether the current runner meets NFR02 for the first release, or whether NFR02's privilege limit must be reported as partially met.
3. **Delivered model configuration.** Apply the pre-written selection rule to the validation results, then confirm the configuration used for the demonstration and the final evaluation: base model, or the adapter on the refactoring role.
4. **Protocol freeze and targets.** Team proposal: before the test run, show the validation baseline tables and the proposed numerical targets (for example a minimum syntax validity and a minimum overall acceptance for the delivered configuration). Then write `experiments/evaluation/protocol-freeze.json` with the generation limits, the evaluation hardware, the model identity and the hashes. Ask whether the supervisor wants to approve the targets before the freeze. R2 question 5 asks the same.
5. **Product behavior for pasted code.** Ask whether "uncertain unless a trusted case is selected" is acceptable for the first release. The alternative, model-generated tests, is outside the scope and is weak evidence ([testing](../development/testing.md)).
6. **Acceptance evidence.** Show the inspected [acceptance matrix](../delivery/acceptance-matrix.md), which links each requirement to code, tests and records. Ask whether this form, together with the handover file described in [acceptance and handover](../agent-execution/06-acceptance-and-handover.md), is what the supervisor expects.

## Supervisor feedback

Empty until the meeting. Record what the supervisor said, separately from the team's proposals above.

- Question 1, feature freeze:
- Question 2, runner safety level:
- Question 3, delivered model configuration:
- Question 4, protocol freeze and targets:
- Question 5, product behavior for pasted code:
- Question 6, acceptance evidence:
- Demonstration shown (commit, mode, cases, outcomes):
- Other feedback:

## Agreed and pending decisions

| Question | Team proposal | Decision recorded at the meeting | Status |
|---|---|---|---|
| 1 Feature freeze | Freeze the documented behavior at the commit shown; fixes only afterwards | | Pending |
| 2 Runner safety level | Report NFR02 as met for trusted cases, without a privilege boundary | | Pending |
| 3 Delivered model configuration | Follow the pre-written validation rule | | Pending |
| 4 Protocol freeze and targets | Show the baseline and targets, then freeze before the test run | | Pending |
| 5 Pasted code ends as `uncertain` | Keep | | Pending |
| 6 Acceptance evidence | T23 matrix and handover file | | Pending |

## Follow-up Issues, owners

Proposed follow-ups. Create them as Issues only after the meeting.

| Follow-up | Owner |
|---|---|
| Inspect the draft acceptance matrix and status, and refresh them when the training and evaluation records exist | Abdullah Tarek, with Abdelrahman Magdy |
| Write `docs/delivery/implementation-handover.md` | Abdelrahman Magdy |
| Record the T22 decision and update the model card (status, prompt version, adapter checksum, validation results) | Abdelrahman Adel |
| Write the protocol freeze record with the agreed targets, limits and hardware | Shahd Abdelhay |
| Update the system design, ADR13, the README status and the execution state | Abdelrahman Magdy |
| Capture the missing interface states and local-model screenshots; align the user guide with the redesigned verification list | Dania El-Walily |

## Conditions for moving to the next phase

- The feature freeze is recorded with its commit.
- The model configuration is selected on validation data only, and the decision is recorded.
- `experiments/evaluation/protocol-freeze.json` exists with status "frozen" and the agreed targets, written before any test-split run.
- The reference runner is enabled on the machine that runs the test evaluation. The harness refuses to start otherwise.
