# R5 review pack: initial delivery and next priorities

Status: Prepared by the team; the meeting has not taken place; no supervisor feedback is recorded.

This pack follows the [review template](review-template.md). A coding agent drafted it on 2026-10-21 for the coordinator, Abdelrahman Magdy. At that time the final evaluation, the report and the release did not exist, so most of this pack is a structure to fill from the records once they exist. It holds no results. Every number added later must come from a committed record and be linked to it. The meeting fields are deliberately left empty.

## Phase, date, and attendees

| Field | Value |
|---|---|
| Phase | P5 Evaluation and initial delivery (roadmap Days 16-21), tasks T24-T28 |
| Tracking Issue | [R5 #33](https://github.com/abdulrhmanmagdy1/grad-refactor-ai/issues/33) |
| Meeting date | Not held. Record the actual date. |
| Attendees | Record at the meeting. |
| Proposed presenters | Shahd Abdelhay (final evaluation and failure analysis), Abdelrahman Adel (final model artifacts and training record), Abdullah Tarek (workflow and verification limits), Abdelrahman Magdy (clean setup and release), Dania El-Walily (report, slides, demonstration) |

## Release or code SHA and links to the demonstration and results

- Release: record the tag and its commit. At preparation no tag existed, and local `main` was at `ee87a11`.
- Demonstration: the [demonstration script](../delivery/demo-script.md), run against the tagged commit in the delivered configuration, with the [presentation outline](../delivery/presentation-outline.md).
- Results: link the evaluation folder written by `scripts/report_evaluation.py` (`experiments/evaluation/<evaluation-id>/`) and the protocol freeze record (`experiments/evaluation/protocol-freeze.json`). Neither existed at preparation.

| Evidence to link when it exists | Owner | State at preparation |
|---|---|---|
| Protocol freeze record with targets | Shahd Abdelhay | Not written; the protocol is a [draft](../evaluation/protocol.md) |
| Test-split evaluation folder (records, summary, tables, figures) | Shahd Abdelhay | Not run |
| Validation evaluation and selection record | Shahd Abdelhay, Abdelrahman Adel | Running on Kaggle; not committed ([R3](r3-integration-and-training.md)) |
| Training record and adapter checksum; updated [model card](../data-and-training/model-card.md) | Abdelrahman Adel | Not committed; the model card said "not trained" |
| Clean-clone setup record (same laptop or second machine) | Abdelrahman Magdy | Not recorded for the current state |
| Acceptance matrix and `docs/delivery/implementation-handover.md` | Abdullah Tarek, Abdelrahman Magdy | Working drafts of the [acceptance matrix](../delivery/acceptance-matrix.md) and the [acceptance status](../delivery/acceptance-status.md) exist, uncommitted and pending inspection. The handover file was not written ([R4](r4-first-release.md)) |
| Report in the university template | Dania El-Walily | Not assembled; workstream notes exist in `docs/report/notes/` |
| Slides, rehearsed demonstration, backup recording | Dania El-Walily | Outline and script prepared; rehearsal and recording pending |
| Release notes, checksums, artifact retrieval instructions | Abdelrahman Magdy | Not written |

## Completed and incomplete outcomes

| Task | Planned output | State at preparation |
|---|---|---|
| T24 Independent final evaluation | Complete results, figures, evaluation section | Not run. The harness refuses the test split without `--i-confirm-frozen-test`, `--protocol-version eval-v1`, a frozen protocol, the local model and matching split hashes ([protocol](../evaluation/protocol.md)). |
| T25 Clean setup and critical fixes | Setup evidence, labelled by hardware coverage | Foundation checks passed on the demonstration laptop on 2026-10-20 ([R1](r1-scope-and-feasibility.md)). CI runs on Linux and Windows. No clean-clone reproduction of the current state was recorded, and no second physical machine has been used. |
| T26 Report and guides | Academic report, user and developer guides | Guides exist ([user guide](../delivery/user-guide.md), [setup](../development/setup.md)). The report is not assembled, and the university template is not confirmed ([delivery checklist](../delivery/checklist.md)). |
| T27 Presentation and repeatable demonstration | Slides, demonstration, backup recording | [Demonstration script](../delivery/demo-script.md) and [presentation outline](../delivery/presentation-outline.md) prepared on 2026-10-21. Rehearsal, local-model screenshots and the backup recording are pending. |
| T28 Initial delivery release | Tag, release notes, checksums | Not started. |

### Results to present (fill from the records)

Fill these tables only from the `summary.md`, CSV tables and `report.json` that `scripts/report_evaluation.py` writes for the test-split run. Every rate uses the number of attempted cases N as its denominator. Report the validation results in a separate table with the same columns, and never present them as test results.

| Arm | N | `proposal_ready` | `rejected` | `uncertain` | `no_change` | `failed` | Syntax valid | Rubric pass | Tests pass | Median latency | Calls per case |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | | | | | | | | | | | |
| B | | | | | | | | | | | |
| C | | | | | | | | | | | |
| D | | | | | | | | | | | |

| Paired comparison | Only first arm accepts | Only second arm accepts | Exact McNemar p | Holm-adjusted p |
|---|---|---|---|---|
| B vs A (coordination, original model) | | | | |
| C vs A (fine-tuning, single role) | | | | |
| D vs C (coordination, adapted role) | | | | |
| D vs B (fine-tuning, multi-role) | | | | |

Also report:

- results by family, because the 88 test cases come from 16 source groups and are not independent;
- the four real-source cases (3 MBPP, 1 HumanEval) separately, as a descriptive probe;
- failure types, timeouts and resource use;
- the targets from the freeze record, and whether they were met;
- the qualitative failure review described in the protocol.

## Problems and alternatives

Known before the evaluation; add what the evaluation shows.

1. **The result may be negative or mixed.** Before any adapter, the base model returned 14 of 24 validation inputs unchanged in the prompt study. Arms A and B may therefore score low, and the effects of fine-tuning and coordination may be small with 88 cases. The [proposal](../proposal/project-proposal.md) treats improvement as a hypothesis, and negative findings are part of the contribution.
2. **Threats to validity.** The template families share one generator design. Held-out families measure transfer to unseen domains, not unseen categories. Real code is a four-case probe, and pretraining overlap cannot be excluded. Reference tests have documented gaps: an untested branch in the card-checksum records, and float-rounding mutants in two test cases ([data plan](../data-and-training/data-plan.md)). The multi-role arms receive oracle feedback from the failing tests in the correction ([R2](r2-data-and-baseline.md), question 6).
3. **Reproduction coverage.** Only one laptop exists. A clean clone on the same laptop proves clean setup only ([roadmap](../planning/roadmap.md)). Training and evaluation may run on Kaggle hardware with another precision ([R3](r3-integration-and-training.md)).
4. **Publication is not settled.** The repository is private and has no open-source license ([NOTICE](../../NOTICE.md)). The team-authored data has no license yet. The adapter's redistribution terms have not been reviewed ([model card](../data-and-training/model-card.md)). Base-model weights are never committed.
5. **Dates and format are unconfirmed.** The official deadline, the report template and the presentation format were not recorded at preparation ([R1](r1-scope-and-feasibility.md), question 6).

## Questions requiring a decision

1. **Reading of the results.** Present the test results against the frozen targets, then ask whether the analysis, including any negative or inconclusive comparison, is sufficient for the evaluation chapter, and which additional analysis is required, if any.
2. **Release content and visibility.** Team proposal: tag a private release with release notes, checksums and retrieval instructions, without base weights. Include the adapter and the team-authored data only after their licenses are decided. Ask whether the department requires public availability, and which license the university expects for student code.
3. **Reproduction evidence.** Ask whether a same-laptop clean-clone reproduction plus the Linux and Windows CI runs is acceptable, or whether a second machine is required.
4. **Report and declaration.** Confirm the template, the length and the declaration of coding-agent assistance agreed at R1 (question 5).
5. **Next priorities after the delivery.** Candidates recorded in the repository, for the supervisor to rank:
   - a second refactoring type from ADR12's alternatives;
   - an operating-system isolation layer for the runner ([runner safety](../development/runner-safety.md));
   - measuring the 1.5B model once resources allow ([second candidate record](../../experiments/models/2026-10-20-second-candidate-not-measured.json));
   - more real-code data;
   - a correction prompt without oracle test details (a new protocol version);
   - comment-preserving targets.

## Supervisor feedback

Empty until the meeting. Record what the supervisor said, separately from the team's proposals above.

- Question 1, reading of the results:
- Question 2, release content and visibility:
- Question 3, reproduction evidence:
- Question 4, report and declaration:
- Question 5, next priorities:
- Demonstration shown (tag, mode, cases, outcomes):
- Other feedback:

## Agreed and pending decisions

| Question | Team proposal | Decision recorded at the meeting | Status |
|---|---|---|---|
| 1 Reading of the results | Report all comparisons as pre-declared, including negative ones | | Pending |
| 2 Release content and visibility | Private tag without base weights; adapter and data after licensing | | Pending |
| 3 Reproduction evidence | Same-laptop clean clone plus CI, labelled as such | | Pending |
| 4 Report and declaration | As agreed at R1 | | Pending |
| 5 Next priorities | No ranking; the supervisor's choice is requested | | Pending |

## Follow-up Issues, owners

Proposed follow-ups. Create them as Issues only after the meeting.

| Follow-up | Owner |
|---|---|
| Final evaluation records, tables, figures, failure analysis and evaluation section | Shahd Abdelhay |
| Final model versions, inference settings, adapter checksums and training section | Abdelrahman Adel |
| Workflow and verification defects; implemented limits for the report | Abdullah Tarek |
| Clean-clone reproduction record, release tag and notes, delivery checklist | Abdelrahman Magdy |
| Report assembly, slides, rehearsed demonstration and backup recording | Dania El-Walily |
| A revised plan for work after Day 21, based on this meeting | Abdelrahman Magdy |

## Conditions for moving to the next phase

The roadmap ends at Day 21. Further work needs a revised plan agreed after this review ([assignments](../planning/assignments.md)). Before that plan:

- The release is tagged at a commit whose evidence is linked here, or the missing items are listed as unmet requirements.
- The decisions above are recorded with the meeting date, and every item still open is listed as pending, not as approved.
