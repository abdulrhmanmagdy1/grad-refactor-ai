# Manual review of 20 records (guard_clauses-v1)

Reviewer: data and evaluation workstream (coding agent working for Shahd Abdelhay), 2026-10-20. To be repeated or confirmed by the owner. This is part of the curation log; the generated log is [curation-log.json](curation-log.json).

## Sample

Seeded with `random.Random("20261020:inspection")`: 10 train, 4 validation and 6 test records, one per family, plus 2 real-source test records. The same 20 ids were reviewed twice: on the first build and again on the final (frozen) dataset after the fixes below.

`gc1-disk-usage-09`, `gc1-sensor-calibration-11`, `gc1-feature-rollout-03`, `gc1-password-strength-09`, `gc1-stock-reservation-03`, `gc1-member-discount-11`, `gc1-ticket-pricing-08`, `gc1-vending-change-04`, `gc1-subscription-renewal-03`, `gc1-bulk-pricing-02` (train); `gc1-parking-fee-05`, `gc1-scholarship-06`, `gc1-version-parse-06`, `gc1-card-checksum-02` (validation); `gc1-mbpp-task-113`, `gc1-mbpp-task-47`, `gc1-quiz-score-03`, `gc1-text-truncate-01`, `gc1-freight-quote-06`, `gc1-atm-withdrawal-03` (test).

## What was checked for every record

1. The original is realistic, valid Python inside the task scope, with nesting that guard clauses can reduce.
2. The target is the expected guard-clause version: same name, signature, docstring and behavior on reading; each special case handled first; remaining logic dedented.
3. The explanation names exactly the conditions that became guard clauses, as written in the target, with the correct action (return value or exception) and the correct nesting depths.
4. For prompts with analysis notes: the line ranges and the "if/else branch ending near line N" statements match the original.
5. Every expected test value, traced by hand from the original; boundary values present where the code compares with a constant.
6. License, source, provenance and split fields are consistent with the source group.

## Findings

- All 20 originals, targets, prompts and explanations were correct. Analysis-note line numbers matched in all 7 sampled records that have notes. All expected values traced by hand agreed with the records, for example `discounted_total(19.99, 'silver', voucher='LOYAL')` = 19.99 x 0.85 = 16.9915, rounded 16.99; `ticket_price(12, 'wed', student=True)` = 11 - 2 - 1 = 8; `check_card_number('000000000000')` is True at the 12-digit length boundary.
- Problem 1 (fixed): explanations with exactly one unlisted guard said "1 more checks exit early". The text now says "1 more check exits early".
- Problem 2 (fixed): some reference tests did not exercise a value cap or rounding in a return expression (`gc1-parking-fee-05` never reached `min(hours * rate, 20)`), so a proposal that dropped the cap would have passed. Two changes: test selection now adds calls with outcomes not yet represented (up to 8 tests), and a mutation operator replaces `min`, `max`, `round`, `abs`, `int` or `float` calls by their first argument, so selection prefers inputs that show the clamp. The final record tests `parking_fee(200, 'van', False)` = 20 (4 hours x 6 = 24, capped). A survivor analysis also added exact boundary values to the value pools of 31 families.
- Observation (documented limitation): tests compare exception types only. In `gc1-atm-withdrawal-03` four different checks raise `ValueError`, so a proposal that reorders two of them would still pass; the contract's `ReferenceExpectation` has no message field.
- Observation: in subset variants where a validation check was dropped (for example `gc1-bulk-pricing-02`), tests use inputs such as a negative price because the function no longer rejects them. The expected values are still the function's real behavior.
- Observation: real-source originals keep their original formatting (`gc1-mbpp-task-113` uses one-space indentation and a backslash continuation); targets are normalized by `ast.unparse`, so the diff for these records also shows formatting changes.
