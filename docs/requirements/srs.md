# Software requirements

This is the first-release specification. Implementation status for each requirement is traced in the acceptance matrix produced at feature freeze (T23); this table states what the release must do. P0 requirements are essential to the agreed release; P1 requirements are included only if time permits.

| ID | Requirement | Acceptance criterion | Priority |
|---|---|---|---|
| FR01 | Accept bounded Python input | Accept non-blank text up to 20,000 characters; reject larger or malformed requests with an understandable response; input outside the [task scope](task-scope.md) (one function of at most 3,000 characters and 60 lines, with the listed exclusions) completes as `no_change` with reason codes and no model call | P0 |
| FR02 | Analyze code | Return structured findings with locations and reasons, or an empty result; the foundation rules cover long functions, including async functions, and nested control blocks; the workflow's analysis reports `nested_conditional` findings whose line ranges lie inside the input | P0 |
| FR03 | Propose a refactoring | Return proposed code, an explanation, and the supported refactoring type (`guard_clauses`, see [task scope](task-scope.md)), or an explicit `no_change` or failure with a reason | P0 |
| FR04 | Verify a proposal | Present syntax, the task rubric, trusted reference-test results and the agent's review as separate results; missing tests never count as a pass | P0 |
| FR05 | Show a diff | Display added and removed lines and the affected components | P0 |
| FR06 | Preserve user control | Allow acceptance, rejection, and download without automatically modifying the original input | P0 |
| FR07 | Trace each run | Record an identifier, configuration, model version, state, duration, and failures | P0 |
| FR08 | Bound execution | Enforce declared limits on calls, retries, generated tokens, and elapsed time: one call in single-role runs, at most five calls and one correction in multi-role runs, per-role token and time limits and a whole-run time limit | P0 |
| FR09 | Compare experiments | Evaluate the agreed variants on the same test cases and export results | P0 |
| FR10 | Retain run history | Retrieve previous results on the demonstration machine | P1 |

## Quality requirements

- NFR01: The API must not execute submitted or generated code. The foundation uses Python AST parsing only.
- NFR02: Any later test execution must use a separate runner with CPU, memory, time, network, filesystem, and privilege limits. The initial release uses trusted examples.
- NFR03: Basic operation must not require a paid API or committed credentials.
- NFR04: The core environment uses Python 3.11 and a lockfile. GPU training dependencies are resolved separately for the actual hardware.
- NFR05: Experiment records must identify the code, data, model revision, configuration, seed, and hardware.
- NFR06: Passing tests must not be presented as proof of full behavioral equivalence.
- NFR07: Response-time and memory targets will be set after measurements on the demonstration machine during P1.

## Main use cases

UC01: Submit a valid example, inspect the proposed change, and download an accepted result.

UC02: Submit invalid Python and receive an error without executing it.

UC03: Encounter a generation or verification failure and see a clear reason rather than a success indicator.

UC04: Run a comparison experiment and export case-level records and a summary.

## Traceability

Implementation Issues identify the relevant requirement IDs. Pull requests include acceptance evidence. Delivery includes a matrix of implemented, deferred, and excluded requirements with links to tests. Requirements that affect the academic scope are confirmed through a recorded supervisor review.
