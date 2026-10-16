# Three-week delivery plan

The first delivery is planned for 21 calendar days from the team's agreed kickoff. Calendar dates and the official university deadline remain unconfirmed. This replaces the previous schedule. Repository setup is complete; the product phases are planned work, not completed milestones.

| Phase | Window | Required outcome | Supervisor review |
|---|---|---|---|
| P1 Scope and feasibility | Days 1-2 (Week 1) | Hardware inventory, one supported refactoring type, measured local inference, tiny LoRA save/reload smoke test or a recorded blocker | R1 on Day 2: scope and resource decision |
| P2 Data and baseline | Days 3-5 (Week 1) | Small licensed dataset, source-separated splits, base-model baseline, shared API/role contracts, frozen comparison protocol | R2 on Day 5: data, baseline and contracts |
| P3 Integration and first training run | Days 6-10 (Weeks 1-2) | One real-model input-to-result case, initial frontend, adapter training and validation evidence if resources permit | R3 on Day 10: demo, actual training status and failures |
| P4 First-release integration | Days 11-15 (Weeks 2-3) | Three bounded roles, trusted-example verification path, honest status display, acceptance checks and feature freeze | R4 on Day 15: readiness for final evaluation |
| P5 Evaluation and initial delivery | Days 16-21 (Week 3) | Frozen-test comparison, critical fixes, clean setup, report, presentation, demo and release | R5 by Day 21: delivery and next priorities |

## Scope that fits the window

Start with one Python file/function and one refactoring type selected using real examples on Day 2. One local web interface, one FastAPI process, one local model shared by three logical roles, and at most one correction attempt are sufficient. Use local files or SQLite for run records. Authentication, public hosting, repository-wide edits, extra languages, multiple model services and optional orchestration frameworks are deferred.

Fine-tuning an existing open-weight model remains a research objective. The plan cannot guarantee its completion before checking hardware. By Day 2, measure inference and a tiny adapter run, including save and reload. If the laptop cannot support training, reduce model/context/batch size or obtain confirmed free university GPU access. Record the blocker and discuss it at R1. A base-model demonstration is useful but does not satisfy the fine-tuning deliverable. Never report it as trained.

## Critical path and daily rhythm

Days 1-2: resources and scope. Days 3-5: data/splits, baseline and contracts. Days 6-10: provider, roles, API and UI converge on a real-model demonstration. Days 11-15: verification and model selection. Days 16-21: final evaluation and delivery.

Use a short daily update in Issues: completed output, next action, blocker and evidence link. Keep one primary implementation task active per person. Reserve Day 21 for final checks and the supervisor discussion, not new features. A phase ending does not automatically complete its tasks.

Schedule the five supervisor discussions at kickoff. Record real feedback after each phase; never mark a review approved before it happens. Independent work can continue while feedback is pending. Scope, data-split and evaluation changes awaiting a decision remain pending.

## Resource and delivery gates

Freeze the test split by Day 5 and never use it for tuning. Demonstrate a real model by Day 10. Freeze core features and model choice by Day 15. Use Days 16-20 for test evaluation, failure analysis, critical fixes and report assembly. If a gate is missed, reduce optional scope and explicitly record incomplete requirements with the supervisor; do not silently change acceptance criteria.

A clean clone and new environment on the same laptop proves clean setup only. Record whether a second physical machine was actually tested. The optional agent execution pack follows the same gates and evidence requirements.

## Ownership and follow-up

See [the person-by-week matrix](assignments.md) and [tasks grouped by owner](by-owner.md). Each task has one accountable owner and no assigned peer reviewer. Each member supplies notes for their work; Dania assembles delivery materials. The optional [agent execution pack](../agent-execution/README.md) does not change human ownership. Improvements after Day 21 require a separate plan based on evaluation and supervisor feedback.
