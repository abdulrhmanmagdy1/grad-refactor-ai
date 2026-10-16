# Optional single-laptop agent execution pack

This folder is a contingency implementation brief for Codex or Claude working in this repository on one laptop. It prepares the work; it does not claim the implementation is complete. The five students retain the workstream ownership in [the team plan](../planning/assignments.md), even when one coding agent implements several components. Humans inspect the final system and explain its work to the supervisor.

## Start here

1. Clone the private repository using the laptop owner's normal GitHub authentication. Never paste credentials into a prompt or commit them.
2. Open the repository root in the coding tool. Read root AGENTS.md and this folder in the order below.
3. Paste [START-PROMPT.md](START-PROMPT.md). Start with repository inspection and the hardware gate, not a new scaffold.
4. Work through the ordered steps, keeping actual evidence and checkpoints. Resume from state, not memory.
5. Deliver the final handover for team inspection. Supervisor meetings and human feedback are recorded only when they occur.

## Reading order

| File | Purpose |
|---|---|
| [START-PROMPT.md](START-PROMPT.md) | Copyable instruction to start or resume the implementation |
| [01-project-brief.md](01-project-brief.md) | Goal, first-release scope, existing code, exclusions and final outcome |
| [02-execution-plan.md](02-execution-plan.md) | Ordered steps, file destinations, dependencies, commands and exit evidence |
| [03-component-contracts.md](03-component-contracts.md) | Proposed interfaces, data records, state transitions and failure behavior |
| [04-data-model-evaluation.md](04-data-model-evaluation.md) | Data preparation, hardware decisions, training and independent evaluation |
| [05-working-and-recovery.md](05-working-and-recovery.md) | Single-laptop setup, Git workflow, state, restart and blocker handling |
| [06-acceptance-and-handover.md](06-acceptance-and-handover.md) | Completion checklist and the team's final inspection |
| [execution-state.template.json](execution-state.template.json) | Machine-readable checkpoint template to copy before work begins |

## Source of truth

Use the actual repository and tests for implementation status. Use [requirements](../requirements/srs.md), [architecture](../architecture/system-design.md), [data plan](../data-and-training/data-plan.md), [training plan](../data-and-training/training-plan.md) and [evaluation protocol](../evaluation/protocol.md) for the full specification. Use [planning/backlog.json](../../planning/backlog.json) and [planning/assignments.json](../../planning/assignments.json) for task dependencies and owners. This folder proposes concrete defaults where a decision is still open; log changes in the architecture decisions before implementation.

Three weeks means Days 1-21 from agreed kickoff, with phase gates on Days 2, 5, 10, 15 and 21. Agent execution does not remove hardware limits, genuine research work, or the supervisor discussions. Do not invent datasets, training runs, successful tests, approvals or citations.
