# Technical decision log

Record context, alternatives, consequences, and evidence for significant decisions. Python input, fine-tuning, GitHub collaboration, and a zero paid-services budget were agreed by the team owner. Other choices remain subject to feasibility and supervisor review; "Implemented" means built and tested in the repository, not approved by the supervisor.

| ID | Decision | Status | Rationale |
|---|---|---|---|
| ADR01 | Python as the input language | Agreed | Limits the task and simplifies verification |
| ADR02 | Fine-tune an existing model | Agreed | Avoids training a code language model from scratch |
| ADR03 | GitHub for shared code, documentation, and tasks | Agreed | Keeps changes and review together |
| ADR04 | Local operation and no paid services | Agreed | Matches the budget |
| ADR05 | Private repository owned by abdulrhmanmagdy1 | Implemented | Preserves the requested ownership and access |
| ADR06 | Python 3.11, uv, and FastAPI | Foundation choice | Provides a locked core environment and inspectable API |
| ADR07 | Fine-tune the modification role first | Implemented in plan | Keeps the first training task bounded |
| ADR08 | Small open-weight model with LoRA | Proposed, measuring | Model size and precision depend on the measured hardware limits (4 GB VRAM) |
| ADR09 | SQLite for local run history | Implemented in contract | Avoids an external database before one is needed |
| ADR10 | Explicit workflow before a dedicated agent framework | Implemented in contract | Establishes behavior before adding framework complexity |
| ADR11 | GitHub storage for distributable artifacts | Feasibility check | Confirm size, quota, and licensing before uploading weights or data |
| ADR12 | Single task: replace nested conditionals with guard clauses | Proposed for R1 | See below |
| ADR13 | One shared task module and one refactoring prompt format | Implemented | See below |
| ADR14 | Model inference in a separate worker process | Implemented in contract | See below |
| ADR15 | Deterministic validation before any model call | Implemented in contract | See below |
| ADR16 | Agent team execution on one laptop | In progress | See below |

## ADR12 - Single supported task: guard clauses

- Status: proposed for the P1 supervisor review. Date: 2026-10-20. Owner: Abdullah Tarek (task scope), recorded by the coordinator.
- Context: the first release supports one narrow refactoring type with explicit inclusion and exclusion rules and reference tests, chosen with measured model examples (T06).
- Alternatives: loop-to-comprehension rewrites; boolean-return simplification; extract-function.
- Decision: Fowler's "Replace Nested Conditional with Guard Clauses" on one small pure function. The rubric is structural and deterministic (nesting depth, signature, docstring, guard present, no new calls), and behavior is checkable with differential reference tests on pure functions. A deterministic AST transformation supplies curated targets.
- Consequences: comments are not preserved in curated targets; ordering comparisons are inverted only against numeric literals (NaN out of scope); conditionals inside loops are not rewritten.
- Evidence: [contracts](contracts.md), tests/test_guard_clauses.py. Measured base-model examples are recorded by the models workstream under experiments/models/.
- Revisit if: the base model cannot produce any valid output on pilot examples, or the supervisor prefers another task.

## ADR13 - Shared task module and refactor-v1 prompt format

- Status: implemented. Date: 2026-10-20. Owner: coordination.
- Decision: src/refactor_ai/tasks/guard_clauses.py and src/refactor_ai/task_format.py are standard-library modules imported by the service, curation, training and evaluation, so the fine-tuned prompt equals the inference prompt. The refactoring role answers with an explanation line and one fenced Python block rather than JSON, which small models produce more reliably. Analysis and review roles use JSON.
- Consequences: changing the prompt requires a new prompt version, regenerated data and a new evaluation protocol version.

## ADR14 - Local model in a worker process

- Status: implemented in contract; implementation owned by the models workstream. Date: 2026-10-20.
- Decision: the API stays in the core environment without PyTorch. A worker process started with the training environment's interpreter loads the pinned model once and serves generation requests over JSON lines. A timeout kills and restarts the worker, which also bounds a generation that cannot be cancelled.
- Consequences: core CI never downloads weights; the first request pays the model load time.

## ADR15 - Deterministic validation first

- Status: implemented in contract. Date: 2026-10-20.
- Decision: the workflow checks the task scope deterministically before any model call; unsupported inputs complete as no_change with zero calls. Model verdicts never override failed deterministic checks.

## ADR16 - Agent team execution

- Status: in progress. Date: 2026-10-20.
- Decision: one coding agent per workstream works in parallel on the agreed contracts on the single laptop (see [team allocation](../agent-execution/team-allocation.md)); the coordinator integrates, and an independent review checks the result. Student ownership is unchanged and every owner inspects their workstream before acceptance.

## New decision record

Include a title, status, date, owner, context, alternatives, decision, consequences, evidence, affected requirements, and a condition for revisiting the choice.
