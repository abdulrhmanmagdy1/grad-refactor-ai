# Eight-week delivery plan

Weeks are relative to the team's agreed start date. The official deadline has not been confirmed. The schedule must be checked against weekly availability at kickoff. Repository setup is complete; the product milestones below are still planned work.

| Phase | Window | Required outcome | Supervisor review |
|---|---|---|---|
| P1 Scope and feasibility | Week 1 | Hardware and availability inventory, bounded tasks, model inference measurements, a small training smoke test, and an agreed scope | Problem, contribution, resources, and report requirements |
| P2 Data and baseline | Week 2 | Licensed and curated data, independent splits, a baseline, acceptance examples, API contracts, and an evaluation protocol | Data quality, task selection, metrics, and experiment design |
| P3 Integration and first training run | Weeks 3-4 | An end-to-end example using the base model, an initial interface, a saved adapter, and preliminary validation results | Demonstration and first before/after comparison |
| P4 First-release integration | Weeks 5-6 | Coordinated roles, a reviewed verification path, diff presentation, bounded retries, and acceptance evidence | Agreed use cases, remaining defects, and feature freeze |
| P5 Evaluation and initial delivery | Weeks 7-8 | Independent evaluation, critical fixes, a second-machine run, report, presentation, demonstration, and release | Results, limitations, delivery feedback, and next priorities |

## Decision points

At the end of Week 1, confirm that the selected task and model fit the training resources. If not, reduce the model, context, or task scope and discuss university GPU access with the supervisor.

At the end of Week 2, freeze the test set. Use validation data, rather than test data, to select prompts and training settings.

By the end of Week 4, demonstrate at least one complete input-to-result case. If integration is late, defer optional features. At the start of Week 7, freeze core features and focus on evaluation, fixes, and delivery.

## Working rhythm

Plan in two-week cycles with a short weekly review and a demonstration at the end of each cycle. Record progress and blockers in Issues. Arrange supervisor reviews before a phase ends, then record decisions and create follow-up tasks. Independent work may continue while a review is pending; decisions that change scope or evaluation wait for agreement.

## Assignments and dependencies

The [assignment table](assignments.md) defines each member's main workstream and outputs in every phase. There is one accountable owner per task and no assigned peer-review role. Scope and dates are updated with supervisor decisions. An assigned task remains in Backlog until its dependencies and acceptance criteria are ready.

## After the first release

Subsequent work will be selected from the evaluation findings: additional refactoring types, better data, larger inputs, improved models, or repository integration. Another programming language or public deployment requires a revised scope and evaluation plan.
