# R5 review pack: initial delivery and next priorities

Status: Prepared by the team; the meeting has not taken place; no supervisor feedback is recorded.

This pack follows the [review template](review-template.md). A coding agent drafted it on 2026-10-21 for the coordinator, Abdelrahman Magdy. At that time the final evaluation, the report and the release did not exist, so most of this pack was a structure to fill from the records. It was updated after commit `74daf25` with the committed results: every number below comes from the [test-split summary](../../experiments/evaluation/test-2026-10-21/targets-report/summary.md) or the records it links. The meeting fields are deliberately left empty.

## Phase, date, and attendees

| Field | Value |
|---|---|
| Phase | P5 Evaluation and initial delivery (roadmap Days 16-21), tasks T24-T28 |
| Tracking Issue | [R5 #33](https://github.com/abdulrhmanmagdy1/grad-refactor-ai/issues/33) |
| Meeting date | Not held. Record the actual date. |
| Attendees | Record at the meeting. |
| Proposed presenters | Shahd Abdelhay (final evaluation and failure analysis), Abdelrahman Adel (final model artifacts and training record), Abdullah Tarek (workflow and verification limits), Abdelrahman Magdy (clean setup and release), Dania El-Walily (report, slides, demonstration) |

## Release or code SHA and links to the demonstration and results

- Release: record the tag and its commit. At preparation no tag existed, and local `main` was at `ee87a11`; at the update `main` was past `74daf25`, still without a tag.
- Demonstration: the [demonstration script](../delivery/demo-script.md), run against the tagged commit in the delivered configuration, with the [presentation outline](../delivery/presentation-outline.md).
- Results: link the evaluation folder written by `scripts/report_evaluation.py` (`experiments/evaluation/<evaluation-id>/`) and the protocol freeze record (`experiments/evaluation/protocol-freeze.json`). Neither existed at preparation. Both exist now: the [test-split evaluation](../../experiments/evaluation/test-2026-10-21/) and the [freeze record](../../experiments/evaluation/protocol-freeze.json).

| Evidence to link when it exists | Owner | State at preparation | State after `74daf25` |
|---|---|---|---|
| Protocol freeze record with targets | Shahd Abdelhay | Not written; the protocol is a [draft](../evaluation/protocol.md) | [Frozen](../../experiments/evaluation/protocol-freeze.json) as eval-v1 with twelve targets |
| Test-split evaluation folder (records, summary, tables, figures) | Shahd Abdelhay | Not run | [Run once](../../experiments/evaluation/test-2026-10-21/) from the clean commit `9582c66` |
| Validation evaluation and selection record | Shahd Abdelhay, Abdelrahman Adel | Running on Kaggle; not committed ([R3](r3-integration-and-training.md)) | [Validation baseline](../../experiments/evaluation/validation-2026-10-21/provenance.json) and [selection record](../../experiments/training/validation-selection-2026-10-20.json) committed |
| Training record and adapter checksum; updated [model card](../data-and-training/model-card.md) | Abdelrahman Adel | Not committed; the model card said "not trained" | [Training record](../../experiments/training/full-2026-10-21.json) and model card committed |
| Clean-clone setup record (same laptop or second machine) | Abdelrahman Magdy | Not recorded for the current state | [Same-laptop clean clone](../../experiments/qa/2026-10-21-clean-clone-reproduction.md) at `74daf25` |
| Acceptance matrix and `docs/delivery/implementation-handover.md` | Abdullah Tarek, Abdelrahman Magdy | Working drafts of the [acceptance matrix](../delivery/acceptance-matrix.md) and the [acceptance status](../delivery/acceptance-status.md) exist, uncommitted and pending inspection. The handover file was not written ([R4](r4-first-release.md)) | All three committed and refreshed ([handover](../delivery/implementation-handover.md)); pending inspection |
| Report in the university template | Dania El-Walily | Not assembled; workstream notes exist in `docs/report/notes/` | [Report](../report/report.md) assembled in Markdown; the template is not confirmed |
| Slides, rehearsed demonstration, backup recording | Dania El-Walily | Outline and script prepared; rehearsal and recording pending | [Slides](../delivery/slides/grad-refactor-ai-presentation.pptx) built from the records; a [dry run](../../experiments/integration/2026-10-21-demo-dry-run.json) of the demonstration cases (all six `proposal_ready` in both workflows); rehearsal and recording pending |
| Release notes, checksums, artifact retrieval instructions | Abdelrahman Magdy | Not written | Not written; checksums are in the model card |

## Completed and incomplete outcomes

| Task | Planned output | State at preparation | State after `74daf25` |
|---|---|---|---|
| T24 Independent final evaluation | Complete results, figures, evaluation section | Not run. The harness refuses the test split without `--i-confirm-frozen-test`, `--protocol-version eval-v1`, a frozen protocol, the local model and matching split hashes ([protocol](../evaluation/protocol.md)). | Done once on Kaggle; results below; the planned qualitative review of sampled proposals has no record yet |
| T25 Clean setup and critical fixes | Setup evidence, labelled by hardware coverage | Foundation checks passed on the demonstration laptop on 2026-10-20 ([R1](r1-scope-and-feasibility.md)). CI runs on Linux and Windows. No clean-clone reproduction of the current state was recorded, and no second physical machine has been used. | Same-laptop clean clone passed; its first attempt found a line-ending defect in two curation hashes, fixed in `74daf25`; CI passed for every push; no second machine |
| T26 Report and guides | Academic report, user and developer guides | Guides exist ([user guide](../delivery/user-guide.md), [setup](../development/setup.md)). The report is not assembled, and the university template is not confirmed ([delivery checklist](../delivery/checklist.md)). | Report assembled in Markdown; guides and the testing page updated; template not confirmed |
| T27 Presentation and repeatable demonstration | Slides, demonstration, backup recording | [Demonstration script](../delivery/demo-script.md) and [presentation outline](../delivery/presentation-outline.md) prepared on 2026-10-21. Rehearsal, local-model screenshots and the backup recording are pending. | Screenshots with the fine-tuned model taken; slides built; rehearsal and recording pending |
| T28 Initial delivery release | Tag, release notes, checksums | Not started. | Not started |

### Results to present (fill from the records)

Fill these tables only from the `summary.md`, CSV tables and `report.json` that `scripts/report_evaluation.py` writes for the test-split run. Every rate uses the number of attempted cases N as its denominator. Report the validation results in a separate table with the same columns, and never present them as test results.

| Arm | N | `proposal_ready` | `rejected` | `uncertain` | `no_change` | `failed` | Syntax valid | Rubric pass | Tests pass | Median latency | Calls per case |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 88 | 7 | 80 | 0 | 0 | 1 | 87 | 13 | 68 | 3.03 s | 1.00 |
| B | 88 | 1 | 85 | 2 | 0 | 0 | 88 | 9 | 69 | 16.02 s | 4.93 |
| C | 88 | 70 | 18 | 0 | 0 | 0 | 88 | 88 | 70 | 7.74 s | 1.00 |
| D | 88 | 35 | 19 | 34 | 0 | 0 | 88 | 88 | 69 | 17.86 s | 3.43 |

Source: the [test-split summary](../../experiments/evaluation/test-2026-10-21/targets-report/summary.md), protocol eval-v1, Kaggle T4 in float32. Validation results are in the [selection record](../../experiments/training/validation-selection-2026-10-20.json) (84 cases per arm) and are not test results.

| Paired comparison | Only first arm accepts | Only second arm accepts | Exact McNemar p | Holm-adjusted p |
|---|---|---|---|---|
| B vs A (coordination, original model) | 0 | 6 | 0.0312 | 0.0312 |
| C vs A (fine-tuning, single role) | 65 | 2 | < 0.0001 | < 0.0001 |
| D vs C (coordination, adapted role) | 1 | 36 | < 0.0001 | < 0.0001 |
| D vs B (fine-tuning, multi-role) | 34 | 0 | < 0.0001 | < 0.0001 |

Also report:

- results by family, because the 88 test cases come from 16 source groups and are not independent;
- the four real-source cases (3 MBPP, 1 HumanEval) separately, as a descriptive probe;
- failure types, timeouts and resource use;
- the targets from the freeze record, and whether they were met;
- the qualitative failure review described in the protocol.

From the records: arm C was accepted in 67 of 84 template cases, 2 of 3 MBPP cases and the one HumanEval case, and arm A in 7 of 84 template cases and none of the real-source cases (results by source group in `by_source_group.csv` of the [targets report](../../experiments/evaluation/test-2026-10-21/targets-report/)). The only failed run was one `unparseable_output` in arm A; no run timed out. Eleven of the twelve targets were met; arm D's `proposal_ready` floor (at least 43.52%) was missed with 35 of 88 (39.8%). The three expected directions were confirmed; for B against A no direction was expected, and A was accepted more often (Holm-adjusted p = 0.031). The qualitative review has not been done.

## Problems and alternatives

Known before the evaluation; what the evaluation showed is item 6.

1. **The result may be negative or mixed.** Before any adapter, the base model returned 14 of 24 validation inputs unchanged in the prompt study. Arms A and B may therefore score low, and the effects of fine-tuning and coordination may be small with 88 cases. The [proposal](../proposal/project-proposal.md) treats improvement as a hypothesis, and negative findings are part of the contribution.
2. **Threats to validity.** The template families share one generator design. Held-out families measure transfer to unseen domains, not unseen categories. Real code is a four-case probe, and pretraining overlap cannot be excluded. Reference tests have documented gaps: an untested branch in the card-checksum records, and float-rounding mutants in two test cases ([data plan](../data-and-training/data-plan.md)). The multi-role arms receive oracle feedback from the failing tests in the correction ([R2](r2-data-and-baseline.md), question 6).
3. **Reproduction coverage.** Only one laptop exists. A clean clone on the same laptop proves clean setup only ([roadmap](../planning/roadmap.md)). Training and evaluation may run on Kaggle hardware with another precision ([R3](r3-integration-and-training.md)).
4. **Publication is not settled.** The repository is private and has no open-source license ([NOTICE](../../NOTICE.md)). The team-authored data has no license yet. The adapter's redistribution terms have not been reviewed ([model card](../data-and-training/model-card.md)). Base-model weights are never committed.
5. **Dates and format are unconfirmed.** The official deadline, the report template and the presentation format were not recorded at preparation ([R1](r1-scope-and-feasibility.md), question 6).
6. **What the evaluation showed.** Fine-tuning helped clearly (C against A). Adding the analysis and review roles lowered acceptance with both models (B against A, D against C), mainly because the untuned review role often repeated itself until the 384-token limit, its verdict became an error and the run ended `uncertain` (34 of D's 88 cases). A reliable review role, or a review that is not taken from the original model, is a prerequisite for the multi-role workflow to help ([report](../report/report.md)).

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
