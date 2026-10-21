# Presentation outline

Status: prepared on 2026-10-21 by a coding agent for Dania El-Walily (T27). It is an outline, not the slides. The department's presentation length and format were not confirmed at preparation ([R1 review pack](../supervisor-reviews/r1-scope-and-feasibility.md), question 6), so the timings assume about 15 minutes of slides plus the 9.5-minute [demonstration](demo-script.md). Shorten the slides, not the demonstration, if less time is given.

The slides built from this outline are in [slides/](slides/grad-refactor-ai-presentation.pptx) (17 slides, with a [PDF copy](slides/grad-refactor-ai-presentation.pdf)); `slides/build_slides.py` rebuilds them from the committed records, and each slide's speaker notes name its source. The results take two slides there (12 and 13), so the interface, demonstration and closing slides are 14 to 16, and 17 is for questions.

Each member presents their own workstream ([team delivery plan](../planning/assignments.md)). No results existed at preparation. The gaps on slides 9 and 12 have since been filled from the committed training record and the test-split summary.

## Speakers

| Member | Workstream | Slides |
|---|---|---|
| Abdelrahman Magdy | Backend, integration and coordination | 1, 2, 5, 15 |
| Abdullah Tarek | Agent workflow and verification | 4, 6, 7 |
| Abdelrahman Adel | Models and training | 8, 9, and the fine-tuning comparisons on slide 12 |
| Shahd Abdelhay | Data, research and evaluation | 3, 10, 11, 12 |
| Dania El-Walily | Frontend and delivery | 13, 14 (demonstration) |

## Slides

### 1. Title and team (Abdelrahman Magdy, 0:30)

- Title: Multi-Agent Refactoring for Python. Show the five members and their workstreams.
- One sentence: a local tool that proposes one refactoring for one small Python function, with each check reported separately, and a study of whether fine-tuning and role coordination make the proposals more reliable.

### 2. Problem, research questions and contribution (Abdelrahman Magdy, 1:00)

- Problem: a model's refactoring can look cleaner and still be unnecessary, invalid or behaviorally wrong.
- The three research questions of the [proposal](../proposal/project-proposal.md): coordination against a single call, the effect of fine-tuning, and whether any gain justifies the cost.
- Contribution: a bounded empirical study (improvement is a hypothesis, not a promise), a reproducible local system, and a documented dataset with frozen splits.

### 3. Related work (Shahd Abdelhay, 1:00)

Six points from the [reading table](../research/related-work.md):

- Fowler defines the task (R1).
- Language models produce unsafe refactorings (R3), which is why the checks are separate.
- Multi-agent refactoring and role-based generation exist with large closed models (R5, R6); this project tests a 0.5B local model.
- Self-repair gains depend on feedback quality and cost (R8).
- LoRA and PEFT make adaptation fit a small GPU (R9, R10).
- Tests can be insufficient (R14), and code datasets leak through duplicates (R15).

### 4. The task: guard clauses (Abdullah Tarek, 1:00)

- The `shipping_cost` before and after from the [task scope](../requirements/task-scope.md).
- One synchronous top-level function, at most 3,000 characters and 60 lines.
- Exclusions with reason codes; the eight-check rubric; the deterministic reference transformation.
- Why this task (ADR12 in the [decision log](../architecture/decisions.md)): the rubric is structural and deterministic, and behavior is checkable on pure functions. State the R1 decision on the task once it is recorded.

### 5. Architecture (Abdelrahman Magdy, 1:00)

- The path: browser, FastAPI service, workflow coordinator, then the model worker process and the isolated reference runner, with SQLite run history behind the service.
- A bounded queue and one worker thread.
- The API parses code and never executes it.
- `/health` reports the actual mode (fake or local model) and the exact model identity ([contracts](../architecture/contracts.md), [backend notes](../report/notes/backend.md)).

### 6. Workflow (Abdullah Tarek, 1:00)

- Deterministic validation first: out-of-scope input ends as `no_change` with zero calls.
- Single-role: exactly 1 call. Multi-role: analysis, refactoring and review, at most 5 calls and 1 correction.
- Strict parsing with at most one deterministic repair; the model is never asked again.
- A run deadline; a run fails when the provider reports another adapter state than requested ([workflow](../architecture/workflow.md)).

### 7. Verification (Abdullah Tarek, 1:00)

- Four dimensions, never merged: syntax, rubric, trusted reference tests, model review.
- The disposition order: `failed`, `no_change`, `rejected`, `uncertain`, `proposal_ready`.
- The runner: static admission, a separate interpreter, Job Object or rlimits, an audit hook, and 19 self-checks that disable execution if any fails.
- Honest limit: it is not a sandbox for hostile code ([runner safety](../development/runner-safety.md)).

### 8. Model and hardware (Abdelrahman Adel, 1:00)

- Qwen2.5-Coder-0.5B-Instruct at a pinned revision (Apache-2.0), on an RTX 2050 with 4 GB.
- Measured: 17.6 s warm load, about 1.0 GB of GPU memory, 13.8 to 26.1 tokens per second. The 1.5B candidate was not measured (disk limit) ([model records](../../experiments/models/README.md)).
- Prompt format: the explanation-first format gave no code block on the pilot functions. The code-first refactor-v2 format parsed 24 of 24 validation outputs, but 14 were unchanged copies ([selection record](../../experiments/models/2026-10-20-prompt-format-selection.md)).

### 9. Fine-tuning (Abdelrahman Adel, 1:00)

- LoRA rank 8 and alpha 16 on the refactoring role, 4.4M trainable parameters (0.88%).
- The pilot: saved, reloaded in a fresh process, interrupted and resumed ([training records](../../experiments/training/README.md)).
- The full run failed on the laptop after 22 of 237 steps (out of virtual memory) and moved to Kaggle's T4 in fp32 ([Kaggle lane](../../training/kaggle/README.md)).
- The validation-only selection rule was written before any comparison.
- From the [training record](../../experiments/training/full-2026-10-21.json): 627 training records, 3 epochs, 120 optimizer steps with an effective batch of 16, 20.5 GPU minutes on a Kaggle T4, training loss 0.69 to 0.01, best validation loss 0.036; adapter weights sha256 `dff9ae02…`.
- The validation decision: arm C 69 of 84 against arm A 6 of 84, so the adapter was adopted ([selection record](../../experiments/training/validation-selection-2026-10-20.json)).

### 10. Dataset and splits (Shahd Abdelhay, 1:00)

- Real code rarely fits the task: 4 of 974 MBPP, 1 of 164 HumanEval, 4 of 2,630 TheAlgorithms functions.
- 799 records: 81 team template families plus 4 real functions.
- 5,168 trusted reference tests, which detect 95.1% of single-point mutants.
- Splits 627 / 84 / 88 by source group; no near-duplicates; the test split frozen by its case-content hash.
- The license of the team-authored data is pending ([data plan](../data-and-training/data-plan.md)).

### 11. Evaluation protocol (Shahd Abdelhay, 1:00)

- Arms A to D, and four paired comparisons: B vs A, C vs A, D vs C, D vs B.
- Primary measure: `proposal_ready` over all attempted cases.
- Exact McNemar tests with a Holm adjustment; results also by family.
- Targets come from the validation baseline and are frozen before the test run.
- The correction's oracle feedback goes only to the multi-role arms ([protocol](../evaluation/protocol.md)).

### 12. Results (Shahd Abdelhay; Abdelrahman Adel for C vs A and D vs B, 2:00)

- From the [test-split summary](../../experiments/evaluation/test-2026-10-21/targets-report/summary.md) and the [freeze record](../../experiments/evaluation/protocol-freeze.json): `proposal_ready` A 7, B 1, C 70, D 35 of 88; C vs A 65 against 2 discordant cases, D vs C 1 against 36, D vs B 34 against 0 (all Holm-adjusted p < 0.0001), B vs A 0 against 6 (p = 0.031); 11 of 12 targets met, D's floor missed; median latency A 3.0 s, C 7.7 s, B 16.0 s, D 17.9 s.
- Show: the arm table with N and every disposition; the four paired comparisons with p-values; the targets and whether they were met; family-level results; cost (calls, latency); two failure examples.
- Label validation results as validation, and never mix them with test results.
- The slides split this into a results slide and a comparisons slide.

### 13. Interface (Dania El-Walily, 0:45)

- The four results shown separately; missing evidence drawn as absent, never as a pass.
- The diff is computed by the application; decisions are records only.
- The fake mode carries a permanent banner.
- WCAG AA contrast is checked by tests in both themes ([frontend notes](../report/notes/frontend.md)).

### 14. Live demonstration (Dania El-Walily, 9:30)

- Follow the [demonstration script](demo-script.md): a success, an unsupported input, and a failed or rejected check, in local-model mode.
- Say the mode before the first run. Abdullah Tarek and Abdelrahman Adel answer questions on the checks and the model.

### 15. Limitations, assistance declaration and future work (Abdelrahman Magdy, 1:30)

- Limitations: one task; a 0.5B model; template-based data; tests that are not proof; a runner that is not a sandbox; one laptop, with training on other hardware.
- The declaration of coding-agent assistance, worded as agreed with the supervisor (R1, question 5; ADR16).
- Future work: the candidates in the [R5 review pack](../supervisor-reviews/r5-delivery.md), question 5.

## Likely examiner questions

Answers are grounded in the repository. Where an answer depends on results, fill it from the records before the presentation. The person named answers first.

**Why "multi-agent" when one model plays every role?** (Abdullah Tarek) The roles are separate prompts with their own output schemas, parsers and budgets. Explicit code coordinates them (ADR10), and the B-vs-A comparison isolates that coordination. One model serves every role because the 4 GB GPU holds one 0.5B model (about 1.0 GB), and the adapter is switched per call, so only the refactoring role uses it (ADR14, [contracts](../architecture/contracts.md)). Whether the title needs a qualification is one of the questions prepared for R1 (the meeting has not taken place).

**Why only one refactoring type?** (Abdullah Tarek) In a three-week window, one task allows a deterministic structural rubric, a deterministic reference transformation for training targets, and behavior checks with reference tests on pure functions (ADR12). The other types considered are listed in ADR12 and named as future work.

**How do you know the refactoring preserves behavior?** (Abdullah Tarek) We do not prove it. The trusted reference tests come from executing the original, and they cover every return and raise of each record. They detect 95.1% of single-point mutants (94.8% with the runner's float tolerance). They are evidence for the tested inputs only. Their known gaps are documented: one untested branch, mutants that only drop a rounding step, and exception messages, which are not compared ([data plan](../data-and-training/data-plan.md)). The rubric checks structure, not behavior.

**Why not let the model write the tests?** (Abdullah Tarek) Tests generated by the model that is being checked are not sufficient evidence for its own changes ([testing](../development/testing.md)), and even human-written tests can be insufficient (R14 in the [reading table](../research/related-work.md)). Model-generated tests are excluded from the [task scope](../requirements/task-scope.md).

**Is it safe to execute model output?** (Abdullah Tarek) Only proposals for the six server-owned demonstration cases are executed. The runner works in layers:

- static admission;
- a separate isolated interpreter with an empty environment;
- operating-system limits (Job Object or rlimits);
- an audit hook;
- 19 self-checks, and execution stays disabled if any check fails.

It is not a sandbox for hostile code: there is no operating-system network, file-system or privilege boundary on the laptop ([runner safety](../development/runner-safety.md)).

**Your data is mostly synthetic. Why trust the results?** (Shahd Abdelhay) Real code rarely has this pattern in a form the task accepts (0.15% to 0.61% yield). The test split uses 12 template families never seen in training, from 12 categories, plus 4 real functions reported separately. Results therefore measure transfer to unseen families with similar skeletons; that limit is reported as a threat to validity.

**How did you avoid tuning on the test set?** (Shahd Abdelhay)

- Splits are by source group, with a near-duplicate check (Allamanis 2019) without the small-function exemption.
- The freeze record holds the case-content hash, and the harness refuses the test split without a frozen protocol.
- The prompt format was selected on validation data only, and the adapter-selection rule was written before any comparison ([freeze record](../../experiments/data/test-split-freeze.json)).

**You re-froze the test split. Is that a problem?** (Shahd Abdelhay) Only the prompt rendering changed, from refactor-v1 to refactor-v2, before any test evaluation. The 88 ids and the case-content hash `3a1e6b95…` are unchanged, and the history is reported ([regeneration record](../../experiments/data/2026-10-20-refactor-v2-regeneration.json)). The question is prepared for R2 (the meeting has not taken place).

**Doesn't the correction see the answers?** (Abdullah Tarek) Partly. The correction prompt shows up to three failing reference tests (call, expected and actual values). Only the multi-role arms B and D get this oracle feedback, and the protocol requires reporting it ([workflow](../architecture/workflow.md)). A correction without test details would need a new protocol version.

**Why such a small model?** (Abdelrahman Adel) The demonstration laptop has a 4 GB GPU and limited disk. The 1.5B model's weights did not fit the free disk ([record](../../experiments/models/2026-10-20-second-candidate-not-measured.json)). Studying a small local model under these limits is part of the question.

**Why train on Kaggle if the system is local?** (Abdelrahman Adel) The full run failed on the laptop after 22 of 237 steps, when Windows ran out of virtual memory with other work running ([record](../../experiments/training/full-2026-10-20-local-attempt1-failed.json)). Training and the validation evaluation moved to a private Kaggle lane with hash-checked bundles. The T4 runs in fp32, and the precision is recorded. Inference for the demonstration stays on the laptop. Whether this is acceptable is one of the questions prepared for R3 (the meeting has not taken place).

**Is the difference between the arms significant?** (Shahd Abdelhay) Each comparison uses a paired exact McNemar test with a Holm adjustment over the four comparisons. The 88 cases come from 16 source groups and are not independent, so results are also reported by family, and conclusions are limited to this task, these cases and this model. Fine-tuning (C vs A, D vs B) and adding the review step (D vs C) differ with Holm-adjusted p < 0.0001; B vs A gives p = 0.031 in favor of A.

**What does the multi-role workflow cost?** (Shahd Abdelhay) Up to 5 model calls instead of 1. On the test split, arm D used 3.43 calls per case and a median of 17.9 s, against 1 call and 7.7 s for arm C, and it was accepted less often (35 against 70), so with the untuned review role the extra cost bought no gain (R8).

**What if fine-tuning had not helped?** (Abdelrahman Adel) The pre-written rule would have kept the base model, and the result would have been reported as found. It did help: 70 against 7 accepted test cases. The negative finding of the study is the review step, which lowered acceptance with both models, and it is reported as such.

**Could the demonstration be staged?** (Dania El-Walily) In fake mode, the service runs the deterministic reference transformation with a placeholder review. `/health` reports the mode, the interface shows a permanent banner, and every fake text starts with `FAKE PROVIDER (not a model):`. The live demonstration runs in local-model mode, with the model identity in the header and in every run record.

**Why does my own code end as "uncertain"?** (Dania El-Walily) Trusted reference tests exist only for the server-owned demonstration cases, and missing tests never count as a pass. This is deliberate ([R4](../supervisor-reviews/r4-first-release.md), question 5).

**Why are comments lost?** (Abdullah Tarek) The reference transformation normalizes code through `ast.unparse`, which drops comments, and the model is asked not to add any. This is a documented limitation and a future-work item.

**Can someone else reproduce this?** (Abdelrahman Magdy)

- The core environment is locked (`uv.lock`), and the model revision and weights are pinned and hash-checked.
- Curation is seeded and rebuilds byte for byte (`curate_dataset.py --check`), and CI runs on Linux and Windows.
- A clean clone from GitHub passed every check, the dataset rebuild and a complete run ([clean-clone record](../../experiments/qa/2026-10-21-clean-clone-reproduction.md)); the first attempt found a line-ending defect in two curation hashes, fixed in `74daf25`.
- Gap: reproduction was on the same laptop only.

**What did coding agents do, and what did you do?** (each speaker for their own workstream) Coding agents implemented the workstreams in parallel on agreed contracts, one per workstream (ADR16, [team allocation](../agent-execution/team-allocation.md)). Each student owns, inspects and must be able to explain their workstream. Use the declaration agreed with the supervisor, and do not overstate either part.

## Before presenting

- Check that the numbers on the slides still match the committed records (rebuild them with `slides/build_slides.py` after any change).
- Confirm the format and the length with the supervisor, and adjust the timings.
- Rehearse the slides and the demonstration together, once, in local-model mode.
- Each speaker rereads their workstream notes in `docs/report/notes/` and the review packs.
