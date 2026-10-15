# Technical decision log

Record context, alternatives, consequences, and evidence for significant decisions. Python input, fine-tuning, GitHub collaboration, and a zero paid-services budget were agreed by the team owner. Other choices remain subject to feasibility and supervisor review.

| ID | Decision | Status | Rationale |
|---|---|---|---|
| ADR01 | Python as the input language | Agreed | Limits the task and simplifies verification |
| ADR02 | Fine-tune an existing model | Agreed | Avoids training a code language model from scratch |
| ADR03 | GitHub for shared code, documentation, and tasks | Agreed | Keeps changes and review together |
| ADR04 | Local operation and no paid services | Agreed | Matches the budget |
| ADR05 | Private repository owned by abdulrhmanmagdy1 | Implemented | Preserves the requested ownership and access |
| ADR06 | Python 3.11, uv, and FastAPI | Foundation choice | Provides a locked core environment and inspectable API |
| ADR07 | Fine-tune the modification role first | Proposed | Keeps the first training task bounded |
| ADR08 | Small open-weight model with LoRA | Proposed | Model size and precision depend on the measured hardware limits |
| ADR09 | SQLite for local run history | Proposed | Avoids an external database before one is needed |
| ADR10 | Explicit workflow before a dedicated agent framework | Proposed | Establishes behavior before adding framework complexity |
| ADR11 | GitHub storage for distributable artifacts | Feasibility check | Confirm size, quota, and licensing before uploading weights or data |

## New decision record

Include a title, status, date, owner, context, alternatives, decision, consequences, evidence, affected requirements, and a condition for revisiting the choice.
