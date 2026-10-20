# Prompt-format selection for the refactoring role (validation only)

**Selection rule, fixed before the outputs were seen:** the variant with the most validation records whose output passes syntax AND the rubric AND the reference tests wins; ties are broken by the parse rate, then by the shorter mean prompt in tokens.

Records: 24 validation records of `datasets/guard_clauses/v1/records.jsonl`, the two lowest ids in each of the 12 validation source groups. Test records were not read and nothing ran on them. Model: Qwen/Qwen2.5-Coder-0.5B-Instruct at `ea3f2471cf1b1f0db85067f1ef93848e38e88c25`, base model without adapter, through `LocalProvider` (greedy, `max_new_tokens` 1,024, `timeout_s` 300). Scoring: `task_format.parse_refactor_output`, `verification.checks` (syntax with `ast`, `guard_clauses.rubric`) and the isolated reference runner from `verification.runner.create_runner("auto")` with each record's tests. Control: all 24 reference targets passed their own tests through the same runner. Commands: `python -m uv run python training/prompt_format_study.py --variants v1,v2,v3,v4` (core environment) and `.venv-train/Scripts/python.exe -X utf8 training/format_token_lengths.py --variants v1,v2,v3 --out experiments/models/2026-10-20-prompt-format-token-lengths.json`. Raw outputs are in [2026-10-20-prompt-format-selection.json](2026-10-20-prompt-format-selection.json).

## Variants

- v1: `task_format.build_refactor_messages` (refactor-v1: explanation first, then the code block).
- v2 (code-first): identical instructions and Code section; the required format is the fenced python block first, then one line `Explanation: <one or two sentences>`.
- v3: v2 plus the last line ``Start your answer with ```python``.
- v4: v2 plus a one-shot before/after example from the pilot functions (`pilot-05`, never from the dataset).

## Results (24 validation records each)

| Variant | Parsed | Syntax pass | Rubric pass | Tests pass | Overall | Unchanged copies | Prompt tokens (mean) | Completion tokens (mean, max) | Latency median / max |
|---|---|---|---|---|---|---|---|---|---|
| v1 | 2/24 | 2/24 | 0/24 | 2/24 | **0/24** | 1 | 280.4 | 153.6, 300 | 5.08 / 12.92 s |
| v2 | 24/24 | 24/24 | 5/24 | 19/24 | **2/24** | 14 | 280.4 | 147.3, 211 | 5.09 / 10.60 s |
| v3 | 24/24 | 24/24 | 4/24 | 21/24 | **2/24** | 16 | 287.4 | 146.6, 211 | 4.91 / 9.73 s |
| v4 | 24/24 | 24/24 | 1/24 | 22/24 | **1/24** | 17 | 399.4 (+119 for the example) | 146.1, 202 | 4.97 / 6.59 s |

No output hit `max_new_tokens`, there were no provider errors, and no output needed a parser repair. Ranking by the rule: v2, v3, v4, v1. v2 and v3 tie on overall (2) and on parse rate (24), and v2 has the shorter prompt.

What the numbers show: putting the code block first removes the format failure completely (2 of 24 parsed with v1, 24 of 24 with v2, v3 and v4), but the untrained base model then usually returns the input unchanged (14 to 17 of 24). Such copies pass the reference tests and fail the rubric. Some changed outputs pass the rubric and fail the tests (v2: gc1-meeting-end-02, gc1-scholarship-01, gc1-scholarship-02), so both checks are needed. The overall passes of v2 and v3 are the same two records of one source group (garden-watering), so the difference between them is not meaningful; the difference between v1 and the code-first formats is. The one-shot example costs 119 prompt tokens and did not help.

## Recommendation

Adopt v2 as refactor-v2. System message unchanged:

```text
You are a careful Python refactoring assistant. You apply exactly the requested refactoring and preserve the program's behavior.
```

User message template (the analysis-notes block exactly as in refactor-v1, only when findings exist):

````text
Task: guard_clauses
Replace the nested conditionals in the function below with guard clauses: handle each special case first with an early return or raise, then continue the main logic without the extra nesting.
Keep the function name, parameters, docstring, return values and raised exceptions exactly the same. Do not add imports, printing, comments or new behavior.
Analysis notes:
- lines {start_line}-{end_line}: {reason}

Respond in exactly this format:
```python
<the complete refactored function>
```
Explanation: <one or two sentences>

Code:
```python
{code.rstrip()}
```
````

That is, in `task_format.py` only `_FORMAT` changes to `("Respond in exactly this format:", "```python", "<the complete refactored function>", "```", "Explanation: <one or two sentences>")`; the training target (`render_refactor_completion`) becomes ``f"```python\n{code.rstrip()}\n```\nExplanation: {explanation}"``. The current `parse_refactor_output` already handles this order without repairs (24 of 24 here), so the parser can stay. The dataset's `prompt` and `completion` fields must be regenerated for refactor-v2.

## Record lengths of the curated train and validation records (max_length 1,024)

| Format | Train mean / max | Validation mean / max | Over 1,024 | Longest records |
|---|---|---|---|---|
| v1 (stored records; `train_lora.py --check-data` gives the same numbers) | 480.9 / 694 | 482.1 / 579 | 0 of 711 | gc1-hex-color-03 (694), gc1-seat-upgrade-07 (688), gc1-letter-grade-02 (683); validation gc1-parcel-shipping-04 (579) |
| v2 | 481.9 / 695 | 483.1 / 580 | 0 of 711 | same records (mean +1.0 token) |
| v3 | 488.9 / 702 | 490.1 / 587 | 0 of 711 | same records (mean +8.0 tokens) |

All curated train and validation records fit the measured training budget of 1,024 tokens in either format.
