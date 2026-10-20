# Agent workflow and verification notes

Workstream: agent workflow and verification (owner Abdullah Tarek). Tasks: T06 task scope, T13 analysis role, T14 refactoring proposals, T19 review and coordination, T20 trusted reference runner, with the workflow part of T23. Written on 2026-10-20 from the implementation and its tests. Every workflow test uses the deterministic fake provider; no model was loaded, so nothing here is evidence of model behavior. The reference runner was exercised with real processes on the Windows demonstration laptop only.

## Components

| File | Responsibility |
|---|---|
| `src/refactor_ai/agents/coordinator.py` | `run_workflow` and `run_workflow_traced`: sequence, budgets, deadline, statuses, error mapping, outcome |
| `src/refactor_ai/agents/prompts.py` | Prompts `analysis-v1`, `review-v1`, `correction-v2`; reuse of the refactoring prompt from `task_format` (`refactor-v2`) |
| `src/refactor_ai/agents/parsing.py` | Strict JSON parsing of analysis and review output with one deterministic repair; finding validation |
| `src/refactor_ai/verification/checks.py` | Syntax (`ast.parse` only), rubric, gated reference tests, summaries for prompts |
| `src/refactor_ai/verification/disposition.py` | Disposition order and `<code>: <sentence>` reasons |
| `src/refactor_ai/verification/diffing.py` | Unified diff and changed lines computed by the application |
| `src/refactor_ai/verification/policy.py` | Static admission policy before execution |
| `src/refactor_ai/verification/runner.py` | `SubprocessReferenceRunner`, limits, result mapping, isolation self-checks, `create_runner` |
| `src/refactor_ai/verification/runner_child.py` | The isolated test process: audit hook, comparison, result channel |
| `src/refactor_ai/verification/_winjob.py` | Windows Job Object through ctypes |
| `src/refactor_ai/verification/registry.py` | Demonstration case allowlist (`CaseRegistry`, `load_cases`) |

Specifications: [task scope](../../requirements/task-scope.md), [workflow](../../architecture/workflow.md), [runner safety](../../development/runner-safety.md).

## Design decisions

- **Deterministic validation decides the scope.** The analysis model cannot turn a supported input into `no_change`; unusable analysis output falls back to the static findings with a warning, as the contract requires.
- **One parse repair, never a second model call.** Analysis and review JSON is parsed strictly, then repaired once (code fence, first JSON object, verdict case). Findings are validated individually so one bad finding does not discard the others.
- **An oversized correction is skipped, not failed.** The correction prompt holds the code twice. When the provider refuses it as `input_too_long` (counted exactly with the model's tokenizer, before generation), the run completes as `correction_input_too_long` with the first proposal and a warning; the coordinator does not estimate tokens itself.
- **A correction is atomic.** It starts only if two calls remain (corrected generation and its review), so the corrected proposal is never left without a review because of the budget.
- **A failed correction keeps the first proposal.** If the corrected answer has no parseable code, the first proposal and its verification are reported with a warning instead of failing the run.
- **Every provider failure fails the run**, in any role, with the provider's error code and the stage; the attempt records keep the evidence gathered so far.
- **Adapter integrity.** A provider that reports a different `use_adapter` than requested fails the run with `model_load_error`, so arms C and D cannot silently run on the base model.
- **Deadline before every step.** The run deadline is checked before each model call and each verification step, and each call's timeout is shortened to the time left. A timeout caused by that shortening is reported as `run_timeout`.
- **Reference tests only for admissible proposals.** A proposal that does not parse or leaves the task constraints is never executed; other rubric failures are still tested because the result is informative.
- **Defense in depth for execution.** Static admission, an isolated interpreter with an empty environment, operating-system limits applied before candidate code runs, and an audit hook; each layer has its own self-check, and the process-count limit is checked with the hook switched off.

## Contract interpretations

- The coordinator never reports `queued`; unsupported input reports only `completed`; every generation is followed by `verifying`, also when its output could not be parsed.
- `attempt_count` counts refactoring calls, including one that failed at the provider.
- `changed_lines` uses the proposal's line numbers (inserted or replaced lines).
- `outcome.model` is the identity of the final proposal's refactoring call; per-call identities are in `WorkflowTrace`.
- A multi-role proposal whose review did not run is `uncertain`, not `proposal_ready`.
- Reference tests with status `pass` but no executed test, or fewer passes than tests, count as `uncertain`.
- A candidate that does not parse is a reference-test `fail` with `missing_function` when the runner is called directly; inside the workflow such a candidate is never sent to the runner (`not_run`).

## Evidence

Commands, run from the repository root on 2026-10-20 (Windows 11, Python 3.11.9):

```bash
python -m uv run pytest tests/test_agents_coordinator.py tests/test_agents_parsing.py tests/test_agents_prompts.py tests/test_verification_checks.py tests/test_verification_registry.py tests/test_runner.py tests/test_runner_child.py
python -m uv run ruff check src/refactor_ai/agents src/refactor_ai/verification
```

The suites cover the multi-role and single-role sequences with exact call counts and status sequences, every unsupported-input reason (zero calls), analysis repair and fallback, refactoring parse errors, syntax and rubric failures, every reference-test status, every review verdict and malformed reviews, the correction path and its exhaustion, the correction and budget switches, provider errors with every error code and in every role, run deadlines, a failing status callback, model-identity checks, the diff and the unchanged original. A shared invariant check runs after every workflow test: call budgets, allowed status transitions, stop reasons consistent with the status, the diff recomputed from the texts, the reason format, and that the outcome can be stored as a `RunRecord`. The disposition order is checked over all 450 combinations of the four dimensions and both modes.

The runner's isolation self-checks passed on the laptop (all 19 checks) and execution is enabled there. The six demonstration cases in `demo_cases.json` load through the registry (`test_shipped_demonstration_cases_load`), their original and reference code pass all 52 tests in the runner, and the workflow with the fake provider and the real runner ends `proposal_ready` for each of them in both modes (`tests/test_runner.py`, shipped-case tests). The Linux path has not been executed by this workstream (no Linux machine or WSL distribution on the laptop); the Ubuntu CI job is the first place it will run.

## Limitations to report

- No model has been run through the workflow; analysis, refactoring and review quality are unmeasured.
- Token budgets (measured with the pinned tokenizer on the CPU, 2026-10-20): realistic inputs at the 3,000-character limit fit every prompt; the review's worst reachable case measured 3,965 of 4,096 tokens; dense code above roughly 2,100 characters skips the correction; digit-dense functions can fail their first prompt with `input_too_long`. Numbers: [workflow token budgets](../../architecture/workflow.md#token-budgets).
- The correction prompt shows failing reference tests to the model (oracle feedback); only multi-role runs get it.
- The runner is not a security boundary for hostile code: no operating-system network, file system or privilege boundary (see [runner safety](../../development/runner-safety.md)).
- Code containing a Markdown fence makes the prompts ambiguous; such runs carry a warning.
