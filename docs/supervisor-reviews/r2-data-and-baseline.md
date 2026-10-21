# R2 review pack: data and baseline

Status: Prepared by the team; the meeting has not taken place; no supervisor feedback is recorded.

This pack follows the [review template](review-template.md). It was drafted on 2026-10-20 by the coding agent working for the coordinator (Abdelrahman Magdy) from the repository records linked below; each presenter checks their part before the meeting. Everything here is evidence and team proposals, not supervisor decisions. The fields for the meeting are deliberately empty.

## Phase, date, and attendees

| Field | Value |
|---|---|
| Phase | P2 Data and baseline (roadmap Days 3-5), tasks T07-T11 |
| Tracking Issue | [R2 #13](https://github.com/abdulrhmanmagdy1/grad-refactor-ai/issues/13) |
| Meeting date | Not held. Record the actual date. |
| Attendees | Record at the meeting. |
| Proposed presenters | Shahd Abdelhay (dataset, splits, leakage, protocol), Abdelrahman Adel (base-model measurements and the prompt format), Abdelrahman Magdy (contracts) |

## Release or code SHA and links to the demonstration and results

- Code: record the exact commit or tag shown. At preparation the repository was at local commit `f8dc49c` with uncommitted work in progress, and no release tag existed. When this pack was refreshed on 2026-10-21, `main` was at `ee87a11`. The P2 evidence entered in local commits `d2d2f0b` (contracts and example JSON), `d377723` (contract-example tests), `446db35` (dataset, splits, evaluation harness) and `f8dc49c` (prompt-format selection and the re-rendered records).
- Demonstration: none is required. Show the records below; the dataset commands are listed in the [data plan](../data-and-training/data-plan.md) if a live check is requested (time them beforehand).

| Evidence | What it shows |
|---|---|
| [Data plan](../data-and-training/data-plan.md), [data and evaluation notes](../report/notes/data-evaluation.md) | Sources, inclusion rules, reference tests, splits, leakage checks |
| [Manifest](../../datasets/guard_clauses/v1/manifest.json), [curation log](../../experiments/data/curation-log.json), [dataset notice](../../datasets/guard_clauses/v1/NOTICE.md) | Counts, hashes, exclusions, licenses and attribution |
| [Manual inspection](../../experiments/data/manual-inspection-2026-10-20.md) | 20 records read in full; two problems found and fixed before the freeze |
| [Repository survey](../../experiments/data/survey-thealgorithms.json) | Yield of qualifying functions in real code |
| [Test-split freeze record](../../experiments/data/test-split-freeze.json), [refactor-v2 regeneration record](../../experiments/data/2026-10-20-refactor-v2-regeneration.json) | Frozen ids and hashes, and the freeze history |
| [Prompt-format selection](../../experiments/models/2026-10-20-prompt-format-selection.md), [benchmark records](../../experiments/models/README.md) | Base-model measurements |
| [Evaluation protocol (draft)](../evaluation/protocol.md), [protocol code](../../src/refactor_ai/evaluation/protocol.py), [harness plumbing check](../../experiments/evaluation/2026-10-20-harness-plumbing-check.json) | Arms, measures, statistics and the harness |
| [Contracts](../architecture/contracts.md), [example JSON](../architecture/examples/README.md) | API, role and run contracts (schema version 1) |

## Completed and incomplete outcomes

| Task | Planned output | State at preparation |
|---|---|---|
| T07 Curated licensed dataset | Versioned data with licenses | Done: 799 records, reproducible byte for byte (`curate_dataset.py --check`). Pending the owner's inspection. |
| T08 Splits and leakage | Source-separated splits, duplicate checks | Done: 627 / 84 / 88 records by source group; no near-duplicates found; test split frozen. |
| T09 Single-role baseline | Baseline results and a reproducible command | Partial: base-model results exist on the pilot functions and on 24 validation records (prompt-format study). The protocol's validation baseline, arms A and B on all 84 validation cases through the workflow, had not been run. At the refresh on 2026-10-21, an evaluation of arms A to D on the 84 validation cases was running on Kaggle ([R3](r3-integration-and-training.md)); its records were not committed. |
| T10 Protocol and targets | Agreed protocol and numerical targets | Draft eval-v1; the harness is implemented and was checked with the fake provider. Not frozen; no targets set. |
| T11 API and role contracts | Shared schemas and example JSON | Done: schema version 1, example JSON exported by a script, contract tests in the backend and a contract mirror test in the frontend. |

### Dataset

| Source | Records | License |
|---|---|---|
| Team template families (81 families in 27 categories) | 795 | `LicenseRef-team-authored-pending`: no redistribution license chosen yet |
| MBPP | 3 | CC-BY-4.0 |
| HumanEval | 1 | MIT |

Real code rarely fits the task: 4 of 974 MBPP functions, 1 of 164 HumanEval functions and 4 of 2,630 top-level functions of TheAlgorithms/Python qualified. Every record has 3 to 10 trusted reference tests (5,168 in total), obtained by executing the trusted original in a curation-only executor; they execute every return and raise statement and detect 95.1% of 10,807 single-point mutants. The six demonstration cases were written for the demonstration, are independent of the dataset and share the pending team license.

| Split | Records | Source groups | Rendered sha256 (refactor-v2) | Case-content sha256 |
|---|---|---|---|---|
| train | 627 | 57 families | `b6a7fc02…` | `e4f075dc…` |
| validation | 84 | 12 families | `d18845b0…` | `b3b44b8f…` |
| test (frozen) | 88 | 12 families, 3 MBPP, 1 HumanEval | `27b6d0ec…` | `3a1e6b95…` |

Leakage: no exact duplicates; no near-duplicates across splits under the Allamanis (2019) rule without the small-function exemption (highest set similarity 0.32); none against the 124 pilot code items (highest 0.42) or the demonstration cases (highest 0.24). The `flag-parse` family was pinned to training because it resembles a pilot function.

### Base-model measurements that exist

Prompt-format study on 24 validation records (two per validation family), base model, refactoring role only, greedy decoding; test records were not read. The selection rule was fixed before the outputs were seen.

| Prompt format | Parsed | Syntax pass | Rubric pass | Tests pass | All checks | Unchanged copies |
|---|---|---|---|---|---|---|
| refactor-v1 (explanation first) | 2 of 24 | 2 of 24 | 0 of 24 | 2 of 24 | 0 of 24 | 1 |
| refactor-v2 (code first) | 24 of 24 | 24 of 24 | 5 of 24 | 19 of 24 | 2 of 24 | 14 |

Unchanged copies pass the reference tests and fail the rubric; some changed outputs pass the rubric and fail the tests, so both checks are needed. The two records that passed every check come from one family (garden-watering). These are not the protocol's baseline and are not evaluation results.

### Re-freeze history of the test split

| Freeze | Prompt rendering | Split sha256 | Case-content sha256 | What happened |
|---|---|---|---|---|
| Wave-1, before any commit (frozen twice) | refactor-v1 | `164ce75e…` | not kept | Superseded the same day: the manual review found reference tests that missed capped or rounded return values, and strengthening them changed the case content. No model or person used this version. |
| Committed in `446db35` | refactor-v1 | `b765dbb8…` | `3a1e6b95…` | Superseded when the prompt format changed |
| Current | refactor-v2 | `27b6d0ec…` | `3a1e6b95…` | Same 88 ids and the same case content; only the prompt rendering changed |

The re-rendering kept all 799 ids and their order; every field other than `prompt`, `completion` and `prompt_version` is byte-identical, and the case-content hashes of all three splits are unchanged. No model or person had been evaluated on the test split at any point.

## Problems and alternatives

1. **Real code rarely matches the task.** The training and held-out data are therefore team-authored template families, which share one generator design; held-out families test transfer to unseen domains with similar skeletons (structural similarity to the nearest training record has a median of about 0.36). The four real functions are a descriptive probe only, and pretraining overlap with these public benchmarks cannot be excluded. Alternatives: mine more repositories (the survey found a 0.15% yield), write real-style functions by hand, or accept the threat to validity and report it (current plan).
2. **No license for the team-authored data.** 795 of 799 records and the six demonstration cases carry `LicenseRef-team-authored-pending`; the [dataset notice](../../datasets/guard_clauses/v1/NOTICE.md) says they should not be redistributed outside the project until a license is chosen, and the repository's [NOTICE](../../NOTICE.md) says university requirements must be confirmed before public distribution.
3. **The baseline is incomplete.** Only the 24-record prompt study exists; the protocol's validation baseline (arms A and B on 84 cases) is needed before the targets can be set.
4. **Generation limits differ between the draft protocol and the service.** At preparation, eval-v1 fixed 384 new tokens for analysis, 768 for refactoring and 384 for review, 2,048 input tokens and 120 s for every call ([protocol code](../../src/refactor_ai/evaluation/protocol.py)), while the service defaults in `WorkflowSettings` ([contracts code](../../src/refactor_ai/contracts.py)) are analysis 384, 2,048, 60 s; refactoring 1,024, 2,048, 120 s; review 768, 4,096, 90 s. The models workstream recommended 1,024 new tokens for refactoring because 768 can cut off the longest realistic functions; in the prompt study the longest refactor-v2 output was 211 tokens. The demonstration would then run with other limits than the evaluation unless one of them changes.
5. **The correction sees failing tests.** The correction prompt shows up to three failing reference tests (call, expected and actual values) to the model. Only the multi-role arms B and D receive this oracle feedback; the protocol requires reporting it ([workflow](../architecture/workflow.md)).
6. **What the tests cannot see.** Reference tests compare exception types, not messages; comments are not preserved in the targets; NaN inputs are out of scope.
7. **Documents to align before the meeting.** At preparation, ADR13 in the [decision log](../architecture/decisions.md) still described the explanation-first refactor-v1 order and the [model card](../data-and-training/model-card.md) named refactor-v1 as the intended prompt, while the contracts, data plan and protocol describe refactor-v2. Owners: the coordinator and the models workstream.

## Questions requiring a decision

1. **License of the team-authored data and demonstration cases.** Ask whether university or department rules govern the license of student-produced data and code. The team then chooses a license (for example a permissive data license) or keeps the records private, and records it in the dataset notice. Until then nothing team-authored leaves the project.
2. **Dataset design.** Confirm that template families for training and held-out families, plus four real functions reported separately, are an acceptable basis for the study, given the threats to validity in problem 1.
3. **The refactor-v2 prompt change.** The prompt was changed to code-first on validation-only evidence (base model: 2 of 24 outputs parsed with refactor-v1, 24 of 24 with refactor-v2), before any test evaluation, and the data were re-rendered with unchanged cases. Ask the supervisor to confirm that this change and its record are methodologically acceptable.
4. **The re-freeze history and the freeze rule.** Confirm that the case-content hash (`3a1e6b95…`) is the invariant of the frozen test split, that a re-rendering for a new prompt version is allowed only with a recorded reason before any test evaluation, and that the history above is reported as is.
5. **The evaluation protocol.** Confirm the primary measure (overall acceptance, disposition `proposal_ready`, over all attempted cases), the four paired comparisons (B vs A, C vs A, D vs C, D vs B) with exact McNemar tests and a Holm adjustment, family-level reporting, and the rule that numerical targets are set from the validation baseline and frozen before the test split is run. Ask whether the supervisor wants to see the targets before the freeze.
6. **Oracle feedback in the correction.** Team proposal: keep it as part of the multi-role design and report it explicitly. Alternative: add a correction variant without test details, which needs a new protocol version and more GPU time.
7. **Generation limits for eval-v1.** Team proposal: reconcile the protocol's limits with the service defaults before the freeze, or record why the evaluation uses different limits from the demonstration. This is a team decision that the supervisor may want to see.

## Supervisor feedback

Empty until the meeting. Record what the supervisor said, separately from the team's proposals above.

- Question 1, data license:
- Question 2, dataset design:
- Question 3, refactor-v2 prompt change:
- Question 4, re-freeze history and freeze rule:
- Question 5, evaluation protocol:
- Question 6, oracle feedback:
- Question 7, generation limits:
- Other feedback:

## Agreed and pending decisions

| Question | Team proposal | Decision recorded at the meeting | Status |
|---|---|---|---|
| 1 Team-authored data license | Decide after the university rules are known; keep private until then | | Pending |
| 2 Dataset design | Template families plus four real functions as a separate probe | | Pending |
| 3 refactor-v2 prompt | Keep refactor-v2 | | Pending |
| 4 Freeze rule and history | Case-content hash as invariant; history reported | | Pending |
| 5 Evaluation protocol | Draft eval-v1 as written | | Pending |
| 6 Oracle feedback | Keep and report | | Pending |
| 7 Generation limits | Reconcile before the freeze | | Pending |

## Follow-up Issues, owners

Proposed follow-ups. Create them as Issues only after the meeting.

| Follow-up | Owner |
|---|---|
| Run the validation baseline (arms A and B, 84 cases) with the local model and report it with the protocol's tables | Shahd Abdelhay, with Abdelrahman Adel for the model runs |
| Reconcile or justify the generation limits of eval-v1 | Shahd Abdelhay, with Abdullah Tarek (workflow defaults) and Abdelrahman Adel |
| Record the chosen data license in the dataset notice and the curation code | Shahd Abdelhay, with Abdelrahman Magdy |
| Align ADR13 and the model card with refactor-v2 | Abdelrahman Magdy (ADR13), Abdelrahman Adel (model card) |

## Conditions for moving to the next phase

- The frozen test split and its freeze rule are accepted, or the required change is recorded as a new dataset or protocol version before any test run.
- The protocol's content is agreed in principle; its freeze record (`experiments/evaluation/protocol-freeze.json`) is written only after the validation baseline and before any test-split run.
- The license path for the team-authored data is agreed before any of it leaves the project.
