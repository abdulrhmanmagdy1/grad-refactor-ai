# Task scope: guard clauses (task version 1)

Status: implemented scope for the first release (T06), proposed for the P1 supervisor review; no supervisor decision has been recorded yet. Owner: Abdullah Tarek (agent workflow and verification). The single definition of the task is [src/refactor_ai/tasks/guard_clauses.py](../../src/refactor_ai/tasks/guard_clauses.py); this page describes that code. If the two disagree, the code is authoritative and this page must be corrected.

## The refactoring

One refactoring type is supported: `guard_clauses`, Fowler's "Replace Nested Conditional with Guard Clauses". A conditional whose branch always ends in `return` or `raise` becomes an early exit (a guard clause), and the remaining logic moves one level to the left. The change is supported only when it lowers the function's maximum control-block nesting depth.

The input is one small, pure Python function. The proposal is the whole refactored function. Behavior is checked with trusted reference tests where a demonstration case provides them; passing those tests is evidence for the tested inputs only, never proof of equal behavior for every input.

## Inclusion rules

An input is supported (`check_input(code).supported`) when all of these hold:

1. It parses as Python and contains exactly one top-level statement: a function definition.
2. It is at most 3,000 characters and 60 lines (`MAX_INPUT_CHARS`, `MAX_INPUT_LINES`).
3. The function is synchronous, undecorated and not a generator.
4. The body has no imports, nested functions or classes, `global`/`nonlocal`, `try`/`with`/`match` blocks, double-underscore names or attributes, and no calls to `open`, `print`, `input`, `exec`, `eval`, `compile`, `__import__`, `globals`, `locals`, `vars`, `setattr`, `delattr`, `breakpoint`, `exit`, `quit` or `help`.
5. At least one `if`/`else` (directly in the function body or in the branches of another `if`) has a branch that always ends in `return` or `raise`, and applying the deterministic rewrite lowers the maximum nesting depth. An `elif` counts at the level of its `if`.

## Exclusion rules and reason codes

Unsupported input completes as disposition `no_change` with zero model calls. Each reason is reported as `<code>: <sentence>` in `verification.disposition_reasons`, and the sentences also appear in `analysis.unsupported_reason`.

| Code | Meaning |
|---|---|
| `syntax_error` | The input is not valid Python |
| `too_long` | More than 3,000 characters or 60 lines |
| `not_single_function` | Anything other than exactly one top-level function (imports or statements outside it, two functions, a class) |
| `async_function` | `async def` or `await` |
| `decorated_function` | A decorator is present |
| `generator_function` | `yield` or `yield from` |
| `nested_definition` | A function or class defined inside the function (a `lambda` is allowed) |
| `imports_present` | An import inside the function |
| `global_or_nonlocal` | `global` or `nonlocal` |
| `try_or_with_present` | A `try` or `with` block |
| `match_present` | A `match` statement |
| `dunder_access` | A double-underscore name or attribute such as `x.__class__` |
| `denied_call:<name>` | A call to one of the denied builtins listed above |
| `no_opportunity` | Valid and in scope, but no conditional can be flattened to lower the nesting depth |
| `unsupported_task_type` | A task type other than `guard_clauses` (workflow only; the API accepts only `guard_clauses`) |

## Before and after examples

Each "after" is the result of `guard_clauses.to_guard_clauses(before)`, the deterministic reference transformation that also produces curated targets and the fake provider's output, shown in the repository's code style. The transformation itself emits `ast.unparse` formatting (for example single-quoted strings) and drops comments; the code shown has exactly the same syntax tree as its output. For every example the rubric passes, and the listed reference tests passed for both versions, exactly as printed here, in the isolated reference runner on the demonstration laptop (2026-10-20).

### 1. Inverted guard for a raising else branch

```python
def shipping_cost(weight, express):
    """Return the shipping cost."""
    if weight > 0:
        if express:
            return weight * 3
        else:
            return weight * 2
    else:
        raise ValueError("weight must be positive")
```

```python
def shipping_cost(weight, express):
    """Return the shipping cost."""
    if weight <= 0:
        raise ValueError("weight must be positive")
    if express:
        return weight * 3
    return weight * 2
```

Nesting depth 2 to 1. Reference tests (`args` -> expected): `[2, True]` -> `6`; `[2, False]` -> `4`; `[0, True]` -> raises `ValueError`; `[-1, False]` -> raises `ValueError`; `[1.5, True]` -> `4.5`.

### 2. Two range checks become two guards

```python
def grade(score):
    if score >= 0:
        if score <= 100:
            if score >= 90:
                result = "A"
            elif score >= 70:
                result = "B"
            else:
                result = "C"
            return result
        else:
            return None
    else:
        return None
```

```python
def grade(score):
    if score < 0:
        return None
    if score > 100:
        return None
    if score >= 90:
        result = "A"
    elif score >= 70:
        result = "B"
    else:
        result = "C"
    return result
```

Nesting depth 3 to 1. The inner `if`/`elif`/`else` assigns instead of returning, so it stays. Reference tests: `[-5]` -> `None`; `[0]` -> `'C'`; `[69]` -> `'C'`; `[70]` -> `'B'`; `[90]` -> `'A'`; `[100]` -> `'A'`; `[101]` -> `None`.

### 3. An elif chain stays flat

```python
def classify(x, y):
    if x is None:
        return "missing"
    elif y:
        if x > 10:
            return "big"
        else:
            return "small"
    else:
        return "other"
```

```python
def classify(x, y):
    if x is None:
        return "missing"
    if not y:
        return "other"
    if x > 10:
        return "big"
    return "small"
```

Nesting depth 2 to 1. `not y` is used because `y` is not a comparison; the rewrite never assumes the operand type. Reference tests: `[None, True]` -> `'missing'`; `[11, True]` -> `'big'`; `[10, True]` -> `'small'`; `[5, 0]` -> `'other'`.

### 4. Negated identity test

```python
def discount(price, member):
    if price is not None:
        if member:
            return price * 0.9
        else:
            return price
    else:
        return 0
```

```python
def discount(price, member):
    if price is None:
        return 0
    if member:
        return price * 0.9
    return price
```

Nesting depth 2 to 1. Reference tests: `[None, True]` -> `0`; `[100, True]` -> `90.0`; `[100, False]` -> `100`; `[0.5, True]` -> `0.45` (floats compared with relative tolerance 1e-9).

## Out-of-scope examples

| Input (abbreviated) | Reason code |
|---|---|
| `def sign(x)` with `if x > 0: return 1` / `elif x < 0: return -1` / `return 0` | `no_opportunity` (already flat) |
| `def pick(flag)` with `if flag: return 1` / `else: return 2` | `no_opportunity` (a guard would not lower the depth) |
| An `if`/`else` inside a `for` loop | `no_opportunity` (conditionals inside loops are not rewritten) |
| `def parse(text)` with `try: return int(text)` / `except ValueError: return None` | `try_or_with_present` |
| `def report(x)` that calls `print(x)` | `denied_call:print` |
| `import math` followed by a function | `not_single_function` |
| Two top-level functions | `not_single_function` |
| `def numbers(n)` containing `yield n` | `generator_function` |
| `return x.__class__` | `dunder_access` |
| A function that defines an inner function | `nested_definition` |

## Rubric

`guard_clauses.rubric(original, candidate)` is a structural check of a proposal. All checks must hold for `rubric: pass`:

| Check | Meaning |
|---|---|
| `parses_as_single_function` | The proposal is one parseable top-level function |
| `same_name` | The function name is unchanged |
| `same_signature` | Parameters, defaults and return annotation are unchanged |
| `same_docstring` | The docstring is unchanged |
| `within_task_constraints` | The proposal stays inside the exclusion rules above |
| `nesting_reduced` | The maximum nesting depth is lower than the original's |
| `has_guard_clause` | At least one `if` without `else` returns or raises |
| `no_new_calls` | No function name is called that the original did not call |

The rubric does not judge behavior. Syntax (`ast.parse`), the rubric, the trusted reference tests and the model review are reported separately; [the workflow page](../architecture/workflow.md) defines how they combine into the disposition.

## Limits and budgets

| Limit | Value | Source |
|---|---|---|
| Request size accepted by the API | 20,000 characters | `MAX_CODE_CHARS`; larger requests are rejected with 422 |
| Task input size | 3,000 characters and 60 lines | preliminary; larger inputs complete as `no_change` with `too_long` |
| Input tokens per call | analysis 2,048, refactoring 2,048, review 4,096 | `WorkflowSettings.generation`; measured fit in the [workflow's token budgets](../architecture/workflow.md#token-budgets) |
| Generated tokens | analysis 384, refactoring 1,024, review 768 | `WorkflowSettings.generation` |
| Model calls, single-role | exactly 1 | refactoring only, no correction |
| Model calls, multi-role | at most 5 | analysis, generation, review, one correction, its review |
| Corrections | at most 1 (multi-role only) | `max_corrections` |
| Time per call | analysis 60 s, refactoring 120 s, review 90 s, each lowered to the time left in the run | `GenerationConfig.timeout_s` |
| Time per run | 600 s | `WorkflowSettings.run_timeout_s` |
| Reference test process | 10 s wall clock, 5 s CPU, 256 MB memory, one process | `RunnerLimits`; see [runner safety](../development/runner-safety.md) |

Token counts were measured with the pinned model's tokenizer (see the [workflow's token budgets](../architecture/workflow.md#token-budgets)). The three longest train and validation records and the six demonstration cases use at most 773 tokens in any prompt. Synthetic functions with ordinary names at the 3,000-character limit used 544 to 792 code tokens, and all their prompts fit. Dense code (short names and many digits) uses more: above roughly 2,100 characters its correction prompt, which holds the code twice, exceeds the refactoring role's 2,048 tokens, and the run completes without the correction (stop reason `correction_input_too_long`). Digits are tokenized one by one, so a function made mostly of long numeric literals can exceed 2,048 tokens already in its first prompt; that run fails with `input_too_long`. An input that exceeds a provider limit is never silently truncated. Changing any budget requires a new evaluation protocol version.

## Outside the three-week release

- Any other refactoring type (extract function, loop-to-comprehension, boolean simplification and others).
- More than one function, classes, methods, whole files or repositories, and other languages.
- Async functions, generators, decorators, `try`/`with`/`match`, imports and nested definitions.
- Rewriting conditionals inside loops, and NaN-aware handling of inverted numeric comparisons.
- Preserving comments and original formatting in the reference transformation.
- Executing arbitrary user-supplied tests or code: only server-owned demonstration cases are executed, in the limited runner.
- Model-generated tests as evidence, automatic changes to the user's files, and any claim of equivalence for all inputs.
