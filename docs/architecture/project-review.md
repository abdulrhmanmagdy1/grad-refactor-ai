# Project review mode (design)

Status: design of 2026-10-21, written by the coordinating coding agent at the request of a team member and updated as the implementation was built. It extends the first release; it is not part of the frozen evaluation eval-v1, and nothing here changes the function-level guard-clause study. Owner of the decision to add it: the team; the supervisor has not reviewed it.

## Goal

A user uploads a whole small Python project as a zip file. The service reviews every Python file and reports, with evidence, problems in five categories: bugs, architecture, security, code quality and refactoring opportunities. For problems that can be fixed inside one function, agents propose a fix, and each fix is verified and reviewed before the user may accept it. The user downloads the accepted fixes as a patch or as a patched copy of the project. The service never changes the user's files in place.

Out of scope: other languages, projects larger than the limits below, fixes that span several functions or files (architecture problems get recommendations, not automatic fixes), installing the project's dependencies, and any claim that a fix is correct for every input.

## Pipeline

The implementation is in [src/refactor_ai/project/](../../src/refactor_ai/project/): `workspace.py` (intake), `index.py`, `rules.py` and `static.py` (deterministic analysis), `agents.py` (prompts and parsers, prompt version project-v5), `fixes.py` (applying and re-checking fixes), `testrun.py` (the project's tests) and `review.py` (the coordinator).

| Stage | Kind | Input | Output |
|---|---|---|---|
| 1. Intake | Deterministic | The uploaded zip | The reviewed files in a workspace, with limits enforced |
| 2. Index | Deterministic | Every `.py` file | Modules, functions and classes with lines, sizes, cyclomatic complexity and nesting; the internal import graph, resolved through package folders and aliases, with cycles and fan-in and fan-out; duplicate function bodies; test files |
| 3. Static scan | Deterministic | The workspace | Findings from ruff (a fixed rule set for bugs, security and quality; it parses and never executes), from mypy on the project's own modules (only error codes that mean a defect: wrong arguments, missing attributes, None used as a value, impossible comparisons; never missing annotations), from three project rules that ruff's stable rules miss (a list changed while iterated, `is` on a computed value, a value only updated from itself), from the index (import cycles, large modules, high fan-out, complex, long or deeply nested functions, many parameters, duplicates, no tests) and from the guard-clause task check. Common rules get a plain-language recommendation |
| 4. Architecture reviewer | Model | The project map from the index, never raw code | At most four issues about named modules. An import cycle the index already found is merged into it; an issue about "external" imports when every external import is standard library is dropped; every other issue goes to the architecture checker, and only issues it judges real are kept, at low severity (a model opinion) |
| 5. Bug finder | Model | One function at a time (the riskiest first: static findings, complexity, size), numbered with file lines, with the findings already known and the start of the project README as the description of intended behavior | At most three suspected bugs, each quoting its line; the first thing it is asked to check is code that does not do what its docstring, name or the README says |
| 6. Quality and security reviewer | Model | Windows of at most 160 lines, cut between top-level statements, riskiest files first, with the start of the README | At most four problems, each quoting its line |
| 7. Finding checker | Model | One model finding with the 17 lines around it | First what the code does and what its docstring and names say it should do, then `real`, `not_a_problem` or `unsure`; only `real` findings are kept. A finding whose quote does not match the file is dropped before this step |
| 7b. Spec tester and spec checker | Model, then the sandboxed test runner | The documented functions, riskiest first (8 by default), each with its module and the start of the README; only when the project's tests are allowed to run | Up to three pytest tests of what the docstring, the name or the README promise, with the expected values taken from the documentation. The tester also sees the signatures of the project modules the function's module imports, so it builds their objects correctly; tests that do not run, or fail by calling the code wrongly (a TypeError, AttributeError, NameError, import or fixture error), go back to it once with the errors to fix how they call the code, and are otherwise set aside. They run on the unchanged project; each failing test goes to the spec checker, which says whether the code or the test is wrong. A failing test blamed on the code becomes a bug finding for the whole function. The passing tests and the blamed ones are kept and run with every fix, so a fix that makes a blamed test pass has the evidence a ready fix needs |
| 8. Fixer | Model, or the deterministic guard-clause rewrite | One function and one problem at a time | The whole corrected function (and any import it needs) and a one-line explanation. Only the function is taken from the answer: stand-in classes or helpers the model writes around it, or a class wrapped around a method, are dropped, and any other module-level code is refused. A function with several problems is fixed step by step; a step is kept only if the file still parses, no new static finding appears and it adds no module-level import of a project module that imports this module back (an import cycle that can fail at import time) |
| 9. Verifier | Deterministic | The project with the function's accepted steps applied | Syntax; the static re-check (the fixed findings' rules are gone and nothing new appears in the function); the project's tests before and after, when enabled |
| 10. Fix reviewer | Model | The problems and the diff | Reasons first, then `accept`, `reject` or `uncertain` |

The coordinator runs the stages in this order, with a budget of model calls and a time limit, and records every call with its raw output. A model finding on a line that a static rule already reports is merged into the static finding, which lists both sources. Without a model (demo mode), only stages 1 to 3, the deterministic guard-clause fixes and the verifier run.

## Findings and fixes

A finding has an id, a category (`bug`, `architecture`, `security`, `quality`, `refactoring`), a severity (`high`, `medium`, `low`), a source (`static:ruff:<rule>`, `static:rule:<rule>`, `static:index:<rule>`, `static:task:guard_clauses` or `agent:<role>`), the other sources that reported it, a file and line range, the enclosing function or module, a title, an explanation, the evidence, a recommendation, and whether it can be fixed inside one function.

There is at most one fix per function, covering the findings its accepted steps fixed. It has four separate checks:

| Check | Values |
|---|---|
| Syntax | The patched file parses: `pass` or `fail` |
| Static re-check | `pass` (the fixed findings' rules are gone, nothing new), `partial` (some are gone, nothing new), `fail` (new findings, or none gone), `not_run` |
| Project tests | `pass` (no test that passed before fails, and some test refers to the function), `fail`, `error`, `not_available` (no tests, or no test refers to the function, so passing tests do not check the fix), `not_run` (turned off) |
| Review | `accept`, `reject`, `uncertain`, `error`, `not_run` (the deterministic rewrite is not reviewed) |

The disposition follows the order of the function mode: `failed` (no fix could be produced), `rejected` (a deterministic check failed, the tests broke or the review rejected), `uncertain` (nothing failed, but tests, the static re-check or the review fell short, or nothing but the model says the change is needed), `proposal_ready` (everything passed). A fix is ready only with machine evidence that it was needed: every problem it fixes is a static finding that the re-check shows is gone, or a test fails before the fix and passes after it. A fix for a problem only the agents report stays `uncertain` with the reason `model_only`, however its other checks went: on the first dev run of the benchmark, the checker accepted a wrong claim, the fixer changed working code, the project's tests did not cover that behavior, the reviewer accepted, and the fix would have been marked ready while breaking a hidden test. Passing tests are evidence for the tested inputs only.

On a sample project of 4 files (the function with five traps from 2026-10-21, a module with `eval` and `os.system`, an import cycle and a test file), the run with the 3B model on the laptop made 30 model calls in about 2 minutes. It reported 11 findings after merging duplicates; the finding checker dropped 9 of 15 model findings. The fixer corrected four bugs of the trap function one at a time, and the tests showed a test that failed before the fix passing after it; the `eval` fix ended `uncertain` because no test calls that function. These are single runs on a hand-made sample, not an evaluation.

## Running the project's tests

Off by default, and allowed only when the service is started with `REFACTOR_AI_PROJECT_TESTS=true`; the person then asks for it per upload. Without that setting a request to run tests is ignored with a warning, so a service that someone else can reach never runs uploaded code. When it is allowed and requested and the project contains tests, the service runs them with pytest once on an unmodified copy (the baseline) and once per fix, each time in a fresh temporary copy of the project, in a separate interpreter: a wall-clock limit; on Windows a Job Object with memory and CPU-time limits and no extra processes; on Linux resource limits, a new session and an unprivileged user when the service runs as root; an empty environment with TEMP inside the copy; and an audit hook, installed after pytest has loaded and before any project code, that refuses network access, new processes, native libraries and writes or deletions outside the copy. Dependencies that are not installed in the service's environment make tests fail with an import error, which is reported as `error`, not as a failed fix. This executes the user's own code on the demonstration machine, which the runner does not isolate completely ([runner safety](../development/runner-safety.md)); the interface says so before the user enables it, and it is meant for the user's own projects only.

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

On the laptop the model loaded in 10.4 s and generated 34 to 37 tokens per second, with 3.6 GB of the GPU in use at the peak. Asked without constraints to list the bugs of a function with five known defects, it named none of them and repeated an invented one, while the deterministic scan found all five ([feasibility record](../../experiments/models/2026-10-21-gguf-3b-feasibility.json)). The deterministic scan is therefore the primary source of findings, model findings must quote the line they are about and are dropped when the quote does not match the file, and every model finding goes through the finding checker and every model fix through the fix reviewer.

## Evaluation (planned)

A benchmark of small projects with known, documented problems (bugs with failing tests, import cycles, security misuse, quality issues and guard-clause opportunities) and clean controls measures, per category: detection recall and precision against the known problems, the share of fixes that pass every check, and the cost (calls, time). Arms: static analysis only; model agents only; the full multi-agent pipeline. The protocol and the benchmark are frozen before the final run, as for eval-v1.
