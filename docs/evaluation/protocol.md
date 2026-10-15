# Evaluation protocol

This draft is to be agreed during P2 before the final test evaluation. The comparison separates the effect of fine-tuning from the effect of role coordination.

## Comparison groups

| Group | Model configuration | Workflow |
|---|---|---|
| A | Original model | One role with the same available verification tools |
| B | Original model | Analysis, refactoring, and review roles |
| C | Fine-tuned modification model | One role |
| D | Fine-tuned modification role; original model for other roles | Analysis, refactoring, and review roles |

Hold data, tool versions, task definitions, and generation settings constant where practical. Declare a total call and token budget and explain its distribution across roles. If equal resource budgets are impractical, report quality alongside elapsed time, calls, and tokens rather than attributing every difference to coordination.

## Measures

- Syntax validity: the proportion of outputs that parse as Python.
- Reference-test preservation: the proportion passing reference tests among cases with those tests, with coverage and case counts shown.
- Refactoring success: compliance with a task-specific rubric without an unintended functional change apparent in the available evidence.
- Overall acceptance: the declared combination of syntax, available reference tests, and rubric, with coverage limitations stated.
- End-to-end and stage latency, calls, tokens, and memory where measurable.
- Task-appropriate structural indicators, such as function length or complexity. A lower indicator alone is not sufficient evidence of success.

Include failures and timeouts in the denominator. Compare the same examples across groups. Report sample size and source diversity, and repeat seeds if resources allow. Do not imply statistical confidence unsupported by the sample.

## Qualitative assessment

Shahd assesses a sample using the fixed task rubric and records ambiguous cases and failure patterns. This is evaluation of model output, not a peer-review assignment between teammates. Model-generated examples are not automatic ground truth.

## Case-level record

Record case ID, source group, split, data/model/code versions, group, seed, input and output references or hashes, syntax and test results, rubric assessment, timing, calls, tokens, failure type, and evaluator. Preserve the full test result record rather than a selected set of successes.

## Release acceptance

The agreed P0 behavior must run on the demonstration machine and a second machine. The release needs reproducible results, an error analysis, documented limitations, and a supervisor review. Numerical targets are set after the baseline and before the final test evaluation. A working prototype does not depend on proving that the research hypothesis is true.
