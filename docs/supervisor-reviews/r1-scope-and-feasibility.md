# R1 review pack: scope and feasibility

Status: Prepared by the team; the meeting has not taken place; no supervisor feedback is recorded.

This pack follows the [review template](review-template.md). It was drafted on 2026-10-20 by the coding agent working for the coordinator (Abdelrahman Magdy) from the repository records linked below; each presenter checks their part before the meeting. Everything here is evidence and team proposals, not supervisor decisions. The fields for the meeting are deliberately empty and must be filled only with what actually happens.

## Phase, date, and attendees

| Field | Value |
|---|---|
| Phase | P1 Scope and feasibility (roadmap Days 1-2), tasks T01-T06 |
| Tracking Issue | [R1 #7](https://github.com/abdulrhmanmagdy1/grad-refactor-ai/issues/7) |
| Meeting date | Not held. Record the actual date. |
| Attendees | Record at the meeting. The [team plan](../planning/assignments.md) asks all five members to attend where available. |
| Proposed presenters | Abdullah Tarek (task scope), Abdelrahman Adel (model benchmark and LoRA pilot), Shahd Abdelhay (related work and data sources), Abdelrahman Magdy (hardware, setup and the decisions to record) |

The [roadmap](../planning/roadmap.md) places this review on Day 2, before the task is fixed. In this run the implementation did not wait for it: the P2 to P4 work was built on 2026-10-20 by one coding agent per workstream ([ADR16](../architecture/decisions.md)). The questions below can still change that work, and each one states what a change would cost.

## Release or code SHA and links to the demonstration and results

- Code: record the exact commit or tag shown at the meeting. At preparation the repository was at local commit `f8dc49c` on `main`, with uncommitted work by other workstreams in progress, and no release tag existed. When this pack was refreshed on 2026-10-21, `main` was at `ee87a11`. The P1 evidence entered in local commits `d2d2f0b` (contracts, task definition, hardware record), `f282276` (task-scope page and examples) and `23c384b` (model benchmark, training environment, LoRA pilot).
- Demonstration: none is required for R1. If the interface is shown, run it in fake mode and say so before the first run: the fake provider applies the deterministic reference transformation, it is not a model (see the [demonstration script](../delivery/demo-script.md)).

| Evidence | What it shows |
|---|---|
| [Hardware record](../../experiments/hardware/2026-10-20-demonstration-laptop.json) | The demonstration laptop and the foundation checks (T01, T02) |
| [Training environment record](../../experiments/hardware/2026-10-20-training-environment.json) | GPU check and the pinned training environment |
| [Related work](../research/related-work.md), [references](../references.md) | T03 reading table of 15 sources checked on their official pages |
| [Model benchmark records](../../experiments/models/README.md) | T04 measurements and the base model's output format |
| [Second candidate record](../../experiments/models/2026-10-20-second-candidate-not-measured.json) | Why the 1.5B model was not measured |
| [LoRA pilot records](../../experiments/training/README.md) | T05 training, save, reload, interruption and resume |
| [Task scope](../requirements/task-scope.md), [ADR12](../architecture/decisions.md) | T06 task definition, examples, rubric and limits |
| [Model notes](../report/notes/model.md), [workflow notes](../report/notes/workflow.md) | The workstreams' own summaries |

## Completed and incomplete outcomes

| Task | Planned output | State at preparation |
|---|---|---|
| T01 Kickoff, hardware and availability | Resource inventory | Hardware recorded for the demonstration laptop. Weekly availability is not recorded in the repository; Issue #1 is the planned place and was not checked for this pack. |
| T02 Reproduce the environment | Setup on all team machines | Foundation checks passed on the demonstration laptop only (doctor, pytest, ruff, docs check, `/health`, `/api/v1/analyze`). No other team machine is recorded. |
| T03 Related work and sources | Reading table, source and license shortlist | Done: 15 primary sources checked; MBPP (CC-BY-4.0) and HumanEval (MIT) licenses verified. Pending the owner's reading. |
| T04 Model benchmark | Model comparison and measured limits | One candidate measured in two runs: Qwen2.5-Coder-0.5B-Instruct. The 1.5B candidate was not downloaded because of the disk limit. |
| T05 LoRA feasibility | Saved and reloaded test adapter | Done on 22 pilot records: trained, saved, reloaded in a fresh process, interrupted and resumed. |
| T06 Task scope | Bounded scope with examples | Implemented as `guard_clauses` task version 1: inclusion and exclusion rules, reason codes, four worked examples with reference tests, rubric and limits. ADR12 is proposed for this review. |

Measured facts to present:

- **Laptop.** Windows 11 Home, AMD Ryzen 7 7435HS (8 cores), 7.8 GB RAM, NVIDIA GeForce RTX 2050 with 4 GB (about 760 MiB used by the desktop), about 9 GB of free disk at the start, no administrator rights, no Docker. It is the only machine available.
- **Model.** Qwen/Qwen2.5-Coder-0.5B-Instruct at revision `ea3f2471cf1b1f0db85067f1ef93848e38e88c25`, Apache-2.0. Load 17.6 s with a warm file cache (88.1 s cold), about 1.0 GB of GPU memory, 13.8 to 26.1 generated tokens per second (median 24.5). Greedy decoding was verified, and outputs were byte-identical across runs.
- **Base model in the first prompt format** (refactor-v1, explanation first). With greedy decoding, 0 of 8 pilot functions and 0 of 1 long input produced a code block; with sampling, 1 of 24 outputs parsed, and it was an unchanged copy of the input. This met the revisit condition written into ADR12.
- **What happened next** (details in [R2](r2-data-and-baseline.md)). With the code-first format refactor-v2, chosen on validation data only, the base model produced code for 24 of 24 validation records, but 14 were unchanged copies and 2 of 24 passed every check.
- **LoRA pilot.** Rank 8, alpha 16, 4,399,104 trainable parameters (0.88%); 16 steps took 20.8 s; total GPU use peaked at 3,896 of 4,096 MiB. Reloaded in a fresh process, the adapter made 12 of 12 pilot outputs parse and 10 of 12 pass the rubric (without it: 1 of 12 parsed, none passed). This is pilot material, not an evaluation, and one adapter output dropped a branch of the original function.
- **Training budget.** About 3.2 GB of the GPU is free with the desktop running. With gradient checkpointing, a 1,024-token record needs 2.8 GB and about 0.87 s per step.

## Problems and alternatives

1. **The base model could not do the task in the first prompt format.** ADR12's revisit condition was met by the pilot benchmark. Alternatives: change the task (ADR12 lists loop-to-comprehension rewrites, boolean-return simplification and extract-function); change the prompt format (done: refactor-v2, see R2); rely on fine-tuning (the pilot adapter made the pilot outputs parse); use a larger model (not possible on this laptop, see the next item).
2. **Only one model was measured.** The bf16 weights of Qwen2.5-Coder-1.5B-Instruct (3.09 GB) and even its 4-bit variant (1.15 GB) did not fit the free disk above the team's floor, and the quantized variants need runtimes outside the tested lock. Alternatives: free disk and measure the 1.5B model; use university GPU time or storage if it exists.
3. **One machine, Windows only.** A clean setup can only be shown on the same laptop. No team machine runs Linux: the reference runner's Linux tests ran only in the Ubuntu CI job, as a non-root user (GitHub Actions run 39418314923, commit `5549a77`), and the case of a root host was added later in `a546f84`. Without administrator rights or Docker there is no operating-system isolation layer ([runner safety](../development/runner-safety.md)). Since this pack was first drafted, GPU training has moved to Kaggle's free GPU because the laptop could not hold the full run ([R3](r3-integration-and-training.md)).
4. **Dates and requirements are unconfirmed.** The university report template, the official deadline and the presentation format are not recorded ([delivery checklist](../delivery/checklist.md)).
5. **The review comes after the work.** The roadmap expects scope approval to follow the feasibility evidence; here the implementation went ahead first. If the supervisor changes the scope, the dependent work must be redone (question 1).

## Questions requiring a decision

1. **Task choice (ADR12).** Team proposal: keep the single task `guard_clauses`, Fowler's "Replace Nested Conditional with Guard Clauses", on one small pure function, as defined in the [task scope](../requirements/task-scope.md). Reasons recorded in ADR12: the rubric is structural and deterministic, behavior can be checked with differential reference tests on pure functions, and a deterministic AST transformation supplies the targets. The failure that triggered the revisit condition was a format failure, which refactor-v2 removed without changing the task. Alternatives: the three listed in ADR12. Cost of a change: a new task version, dataset, prompt, training run, evaluation protocol and demonstration cases.
2. **Model and resources (ADR08).** Team proposal: accept Qwen2.5-Coder-0.5B-Instruct as the only measured candidate under the 4 GB GPU and disk limits. Ask whether a second candidate must be measured, and whether the university can provide GPU time or storage. The use of Kaggle's free GPU since then is R3 question 1.
3. **Academic scope.** Confirm that one refactoring type, one Python function per run and the exclusions listed under "Outside the three-week release" in the task scope meet the department's requirements. Confirm the three research questions of the [project proposal](../proposal/project-proposal.md) and that a negative result is an acceptable outcome.
4. **Title wording.** The analysis, refactoring and review roles are separate prompts and schemas served by one shared base model and coordinated by explicit code ([contracts](../architecture/contracts.md), ADR10, ADR14). Ask whether "Multi-Agent" in the title needs a qualification, for example "multi-role workflow on one local model".
5. **Coding-agent assistance (ADR16).** The implementation was produced by coding agents, one per workstream, while each student owns and must inspect their workstream ([team allocation](../agent-execution/team-allocation.md), [acceptance and handover](../agent-execution/06-acceptance-and-handover.md)). Ask whether this is acceptable under the department's rules and how it must be declared in the report and the presentation.
6. **Logistics.** The report template, the official deadline, the presentation length and format, and whether R1 to R3 can be held in one meeting because their work already exists.

## Supervisor feedback

Empty until the meeting. Record what the supervisor said, separately from the team's proposals above.

- Question 1, task choice:
- Question 2, model and resources:
- Question 3, academic scope:
- Question 4, title wording:
- Question 5, coding-agent assistance:
- Question 6, logistics:
- Other feedback:

## Agreed and pending decisions

| Question | Team proposal | Decision recorded at the meeting | Status |
|---|---|---|---|
| 1 Task choice (ADR12) | Keep `guard_clauses` task version 1 | | Pending |
| 2 Model and resources (ADR08) | Qwen2.5-Coder-0.5B-Instruct as the only candidate | | Pending |
| 3 Academic scope | The scope of the task-scope page | | Pending |
| 4 Title wording | No proposal; the supervisor's preference is requested | | Pending |
| 5 Coding-agent assistance | No proposal; follow the department's rules | | Pending |
| 6 Logistics | No proposal | | Pending |

## Follow-up Issues, owners

Proposed follow-ups. Create them as Issues only after the meeting, and only those that the decisions require.

| Follow-up | Owner |
|---|---|
| Record the outcome in ADR12 and ADR08 with the meeting date | Abdelrahman Magdy |
| If the task changes: a new task version, examples and rubric | Abdullah Tarek, with Shahd Abdelhay (data) and Abdelrahman Adel (training) |
| If requested: measure a second model candidate | Abdelrahman Adel |
| Record weekly availability in Issue #1 | Abdelrahman Magdy |
| Add the agreed declaration of coding-agent assistance to the report plan | Dania El-Walily |

## Conditions for moving to the next phase

- The task decision and the model and resource decision are recorded with the meeting date ("R1 on Day 2: scope and resource decision" in the roadmap).
- The training feasibility status is accepted: the pilot adapter was saved and reloaded, or the supervisor states another requirement.
- If the task or the model changes, the P2 to P4 work that depends on it is marked for rework before any evaluation result is reported.
