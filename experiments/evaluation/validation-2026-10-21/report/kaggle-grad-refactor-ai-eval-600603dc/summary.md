# Evaluation summary

- Protocol: eval-v1 (status: draft)
- Split: validation (sha256 d18845b04bf7800ac1db82bc2d93f441253b2a012d9a5cb6f058b0d8a111c2e5), 84 cases
- Dataset sha256: 299b4f7fca170d2a9260319f6c1f81e832d54114c8bdd51959d6aeb8b23ff2e3
- Evaluation ids: kaggle-grad-refactor-ai-eval-600603dc
- Provider modes: local_model
- Code: None

Every rate below uses all attempted cases of the arm as its denominator, so failures and timeouts count against the arm. Passing reference tests supports behavior preservation only on the tested inputs.

## Outcomes by arm

| Measure | A | B | C | D |
|---|---|---|---|---|
| Run completed | 83/84 (98.8%) | 84/84 (100.0%) | 84/84 (100.0%) | 84/84 (100.0%) |
| Run failed (any reason) | 1/84 (1.2%) | 0/84 (0.0%) | 0/84 (0.0%) | 0/84 (0.0%) |
| Timed out (provider or run) | 0/84 (0.0%) | 0/84 (0.0%) | 0/84 (0.0%) | 0/84 (0.0%) |
| Proposal parses (syntax pass) | 83/84 (98.8%) | 84/84 (100.0%) | 84/84 (100.0%) | 84/84 (100.0%) |
| Task rubric pass | 17/84 (20.2%) | 16/84 (19.0%) | 84/84 (100.0%) | 84/84 (100.0%) |
| Reference tests pass | 66/84 (78.6%) | 69/84 (82.1%) | 69/84 (82.1%) | 69/84 (82.1%) |
| Reference tests executed | 83/84 (98.8%) | 84/84 (100.0%) | 84/84 (100.0%) | 84/84 (100.0%) |
| Overall acceptance (proposal_ready) | 6/84 (7.1%) | 3/84 (3.6%) | 69/84 (82.1%) | 46/84 (54.8%) |
| Rejected | 77/84 (91.7%) | 79/84 (94.0%) | 15/84 (17.9%) | 15/84 (17.9%) |
| Uncertain | 0/84 (0.0%) | 2/84 (2.4%) | 0/84 (0.0%) | 23/84 (27.4%) |
| No change | 0/84 (0.0%) | 0/84 (0.0%) | 0/84 (0.0%) | 0/84 (0.0%) |
| Harness recheck disagrees with workflow | 0/84 (0.0%) | 0/84 (0.0%) | 0/84 (0.0%) | 0/84 (0.0%) |
| Reference tests pass, of executed | 66/83 (79.5%) | 69/84 (82.1%) | 69/84 (82.1%) | 69/84 (82.1%) |

## Cost by arm

| Measure | A | B | C | D |
|---|---|---|---|---|
| Latency median (s) | 4.08 | 15.54 | 9.74 | 15.81 |
| Latency p90 (s) | 5.15 | 32.85 | 11.20 | 26.02 |
| Latency mean (s) | 4.34 | 20.30 | 9.65 | 18.79 |
| Calls per case (mean) | 1.00 | 4.86 | 1.00 | 3.36 |
| Calls (total) | 84 | 408 | 84 | 282 |
| Tokens per case (mean; cases with counts) | 432.8 (84/84) | 2851.7 (84/84) | 485.6 (84/84) | 1850.8 (84/84) |
| Worker peak RSS MB (max; cases measured) | 2253.9 (84) | 2253.9 (84) | 2253.9 (84) | 2253.9 (84) |
| GPU memory used MB (max; cases measured) | 2395 (84) | 2395 (84) | 2395 (84) | 2395 (84) |
| Budget or adapter warnings | 0 | 0 | 0 | 0 |

## Failure types by arm

- A: none: 83, unparseable_output: 1
- B: none: 84
- C: none: 84
- D: none: 84

## Paired comparisons (overall acceptance)

Exact McNemar test on discordant cases; Holm adjustment over the comparisons shown.

| Comparison | Effect isolated | Paired cases | First only | Second only | Both | Neither | p (exact) | p (Holm) |
|---|---|---|---|---|---|---|---|---|
| B vs A | role coordination, original model | 84 | 2 | 5 | 1 | 76 | 0.4531 | 0.4531 |
| C vs A | fine-tuning, single role | 84 | 65 | 2 | 4 | 13 | 0.0000 | 0.0000 |
| D vs C | role coordination, adapted refactoring role | 84 | 2 | 25 | 44 | 13 | 0.0000 | 0.0000 |
| D vs B | fine-tuning, multi-role | 84 | 44 | 1 | 2 | 37 | 0.0000 | 0.0000 |

## Overall acceptance by source

| Arm | Source | Accepted |
|---|---|---|
| A | team-template | 6/84 (7.1%) |
| B | team-template | 3/84 (3.6%) |
| C | team-template | 69/84 (82.1%) |
| D | team-template | 46/84 (54.8%) |
