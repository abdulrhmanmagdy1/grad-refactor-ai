# Project review mode (design)

Status: design of 2026-10-21, written before the implementation by the coordinating coding agent at the request of a team member. It extends the first release; it is not part of the frozen evaluation eval-v1, and nothing here changes the function-level guard-clause study. Owner of the decision to add it: the team; the supervisor has not reviewed it.

## Goal

A user uploads a whole small Python project as a zip file. The service reviews every Python file and reports, with evidence, problems in five categories: bugs, architecture, security, code quality and refactoring opportunities. For problems that can be fixed inside one function, agents propose a fix, and each fix is verified and reviewed before the user may accept it. The user downloads the accepted fixes as a patch or as a patched copy of the project. The service never changes the user's files in place.

Out of scope: other languages, projects larger than the limits below, fixes that span several functions or files (architecture problems get recommendations, not automatic fixes), installing the project's dependencies, and any claim that a fix is correct for every input.

## Pipeline

| Stage | Kind | Input | Output |
|---|---|---|---|
| 1. Intake | Deterministic | The uploaded zip | A safe, read-only copy of the project's Python files in a workspace, with limits enforced |
| 2. Index | Deterministic | Every `.py` file | Modules, functions and classes with their lines, sizes and cyclomatic complexity; the internal import graph with cycles and fan-in and fan-out; test files |
| 3. Static scan | Deterministic | The workspace | Findings from ruff (a curated rule set for bugs, security and quality, JSON output, no code execution), from the index (import cycles, oversized modules and functions, deep nesting, duplicate functions) and from the guard-clause task check |
| 4. Bug agent | Model | One function at a time, with the static findings already known for it | Additional suspected bugs with line, explanation, severity and confidence |
| 5. Quality and security agent | Model | One file at a time (or a window of it), with its static findings | Code-quality and security problems that rules do not cover |
| 6. Architecture agent | Model | A compact project map from the index (modules, sizes, dependencies, cycles, metrics), never raw code | Architecture problems and a recommendation for each; no automatic fix |
| 7. Fixer agent | Model, or the deterministic guard-clause rewrite | One fixable finding and its enclosing function | The whole revised function and a one-line explanation |
| 8. Verifier | Deterministic | The project with one fix applied | Syntax of the patched file; a static re-scan (the finding's rule no longer fires and no new finding appears in the function); the project's tests before and after the fix, when enabled |
| 9. Reviewer agent | Model | The finding, the original and revised function and the diff | accept, reject or uncertain, with reasons |
| 10. Report | Deterministic | Everything above | Findings grouped by category and severity, the architecture section, and each fix with its checks and disposition |

The coordinator runs the stages in this order, with a budget of model calls and a time limit for the whole run, and records every call. Model calls are ranked by risk so that a project larger than the budget still gets its riskiest functions reviewed: functions with static findings first, then by complexity and size. Static and model findings on the same lines with the same meaning are merged, keeping both sources.

## Findings and fixes

A finding has an id, a category (`bug`, `architecture`, `security`, `quality`, `refactoring`), a severity (`high`, `medium`, `low`), a source (`static:ruff:<rule>`, `static:index:<rule>`, `static:task:guard_clauses` or `agent:<role>`), a file and line range, a title, an explanation, the evidence (the rule's message or the agent's reason), a confidence for model findings, and whether it can be fixed inside one function.

A fix has the four separate checks of the function mode, adapted to a project:

| Check | Values |
|---|---|
| Syntax | The patched file parses: `pass` or `fail` |
| Static re-scan | The finding's rule no longer fires and the function has no new finding: `pass`, `fail` or `not_run` |
| Project tests | The tests that passed before the fix still pass, and a test that failed may now pass: `pass`, `fail`, `error`, `not_available` (no tests), `not_run` (disabled or out of budget) |
| Review | `accept`, `reject`, `uncertain`, `error`, `not_run` |

The disposition follows the same order as in the function mode: `failed` (no fix could be produced), `rejected` (a deterministic check failed or the review rejected), `uncertain` (nothing failed, but tests or review are missing), `proposal_ready` (everything passed). Passing tests are evidence for the tested inputs only.

## Running the project's tests

Off by default. When the user enables it and the project contains pytest or unittest tests, the service runs them once on an unmodified copy (the baseline) and once per verified fix, each time in a fresh temporary copy of the project, in a separate interpreter with the limits of the reference runner: wall-clock and CPU time, memory, process count, an empty environment, network and writes outside the copy refused by the audit hook. Dependencies that are not installed in the service's environment make tests fail with an import error, which is reported as `error`, not as a failed fix. This executes the user's own code on the demonstration machine, which the runner does not isolate completely ([runner safety](../development/runner-safety.md)); the interface says so before the user enables it, and it is meant for the user's own projects only.

## Limits

| Limit | Value |
|---|---|
| Zip size | 5 MB |
| Python files | 200 |
| Total Python source | 1.5 MB |
| One file sent to a model | windows of at most 160 lines |
| Model calls per run | 80 |
| Run time | 45 minutes |
| Fixes verified with tests | 20 |

Zip entries with absolute paths, `..`, links or names outside the workspace are refused, and only `.py`, `.toml`, `.cfg`, `.ini`, `.txt` and `.md` files are extracted.

## Model

The project mode uses Qwen2.5-Coder-3B-Instruct, quantized to 4 bits (GGUF `q4_k_m`, 2.1 GB), served by llama.cpp on the laptop's 4 GB GPU through the same worker protocol as the function mode ([gguf.py](../../src/refactor_ai/providers/gguf.py), [gguf_worker.py](../../src/refactor_ai/providers/gguf_worker.py), [example settings](../../configs/model.project.example.json)). These are new modules: the provider files frozen by protocol eval-v1 are not changed. Its license is the Qwen Research License (non-commercial research use), unlike the Apache-2.0 0.5B model, and must be named in the report. Only one model is resident on the GPU at a time: `ModelPool` stops the other model's worker before a call, so switching modes costs one model load.

On the laptop the model loaded in 10.4 s and generated 34 to 37 tokens per second, with 3.6 GB of the GPU in use at the peak. Asked without constraints to list the bugs of a function with five known defects, it named none of them and repeated an invented one, while the deterministic scan found all five ([feasibility record](../../experiments/models/2026-10-21-gguf-3b-feasibility.json)). The deterministic scan is therefore the primary source of findings, model findings must quote the line they are about and are dropped when the quote does not match the file, and every model finding and fix goes through the review agent.

## Evaluation (planned)

A benchmark of small projects with known, documented problems (bugs with failing tests, import cycles, security misuse, quality issues and guard-clause opportunities) and clean controls measures, per category: detection recall and precision against the known problems, the share of fixes that pass every check, and the cost (calls, time). Arms: static analysis only; model agents only; the full multi-agent pipeline. The protocol and the benchmark are frozen before the final run, as for eval-v1.
