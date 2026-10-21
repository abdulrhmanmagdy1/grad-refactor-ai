# Evaluation summary

- Protocol: eval-v1 (status: frozen)
- Split: test (sha256 27b6d0ece9430ee30a96617949a31e1c71a0a5c0be7187b36bc660d998e95633), 88 cases
- Dataset sha256: 299b4f7fca170d2a9260319f6c1f81e832d54114c8bdd51959d6aeb8b23ff2e3
- Evaluation ids: kaggle-grad-refactor-ai-eval-3ba44332
- Provider modes: local_model
- Code: 9582c662850eeb6c5495cd2124138aa4cfd04714

Every rate below uses all attempted cases of the arm as its denominator, so failures and timeouts count against the arm; syntax, rubric and reference-test successes count only for completed runs. Reference tests count as executed when at least one test produced a result. Passing reference tests supports behavior preservation only on the tested inputs.

## Outcomes by arm

| Measure | A | B | C | D |
|---|---|---|---|---|
| Run completed | 87/88 (98.9%) | 88/88 (100.0%) | 88/88 (100.0%) | 88/88 (100.0%) |
| Run failed (any reason) | 1/88 (1.1%) | 0/88 (0.0%) | 0/88 (0.0%) | 0/88 (0.0%) |
| Timed out (provider or run) | 0/88 (0.0%) | 0/88 (0.0%) | 0/88 (0.0%) | 0/88 (0.0%) |
| Proposal parses (syntax pass) | 87/88 (98.9%) | 88/88 (100.0%) | 88/88 (100.0%) | 88/88 (100.0%) |
| Task rubric pass | 13/88 (14.8%) | 9/88 (10.2%) | 88/88 (100.0%) | 88/88 (100.0%) |
| Reference tests pass | 68/88 (77.3%) | 69/88 (78.4%) | 70/88 (79.5%) | 69/88 (78.4%) |
| Reference tests executed | 87/88 (98.9%) | 88/88 (100.0%) | 88/88 (100.0%) | 88/88 (100.0%) |
| Overall acceptance (proposal_ready) | 7/88 (8.0%) | 1/88 (1.1%) | 70/88 (79.5%) | 35/88 (39.8%) |
| Rejected | 80/88 (90.9%) | 85/88 (96.6%) | 18/88 (20.5%) | 19/88 (21.6%) |
| Uncertain | 0/88 (0.0%) | 2/88 (2.3%) | 0/88 (0.0%) | 34/88 (38.6%) |
| No change | 0/88 (0.0%) | 0/88 (0.0%) | 0/88 (0.0%) | 0/88 (0.0%) |
| Harness recheck disagrees with workflow | 0/88 (0.0%) | 0/88 (0.0%) | 0/88 (0.0%) | 0/88 (0.0%) |
| Reference tests pass, of executed | 68/87 (78.2%) | 69/88 (78.4%) | 70/88 (79.5%) | 69/88 (78.4%) |

## Cost by arm

| Measure | A | B | C | D |
|---|---|---|---|---|
| Latency median (s) | 3.03 | 16.02 | 7.74 | 17.86 |
| Latency p90 (s) | 4.95 | 31.16 | 10.77 | 29.99 |
| Latency mean (s) | 3.55 | 20.17 | 8.27 | 18.78 |
| Calls per case (mean) | 1.00 | 4.93 | 1.00 | 3.43 |
| Calls (total) | 88 | 434 | 88 | 302 |
| Tokens per case (mean; cases with counts) | 381.1 (88/88) | 2704.5 (88/88) | 433.6 (88/88) | 1811.7 (88/88) |
| Worker peak RSS MB (max; cases measured) | 2258.5 (88) | 2258.5 (88) | 2258.5 (88) | 2258.5 (88) |
| GPU memory used MB (max; cases measured) | 2615 (88) | 2615 (88) | 2615 (88) | 2615 (88) |
| Budget or adapter warnings | 0 | 0 | 0 | 0 |

## Failure types by arm

- A: none: 87, unparseable_output: 1
- B: none: 88
- C: none: 88
- D: none: 88

## Paired comparisons (overall acceptance)

Exact McNemar test on discordant cases; Holm adjustment over the comparisons shown.

| Comparison | Effect isolated | Paired cases | First only | Second only | Both | Neither | p (exact) | p (Holm) |
|---|---|---|---|---|---|---|---|---|
| B vs A | role coordination, original model | 88 | 0 | 6 | 1 | 81 | 0.0312 | 0.0312 |
| C vs A | fine-tuning, single role | 88 | 65 | 2 | 5 | 16 | 0.0000 | 0.0000 |
| D vs C | role coordination, adapted refactoring role | 88 | 1 | 36 | 34 | 17 | 0.0000 | 0.0000 |
| D vs B | fine-tuning, multi-role | 88 | 34 | 0 | 1 | 53 | 0.0000 | 0.0000 |

## Overall acceptance by source

| Arm | Source | Accepted |
|---|---|---|
| A | humaneval | 0/1 (0.0%) |
| A | mbpp | 0/3 (0.0%) |
| A | team-template | 7/84 (8.3%) |
| B | humaneval | 0/1 (0.0%) |
| B | mbpp | 0/3 (0.0%) |
| B | team-template | 1/84 (1.2%) |
| C | humaneval | 1/1 (100.0%) |
| C | mbpp | 2/3 (66.7%) |
| C | team-template | 67/84 (79.8%) |
| D | humaneval | 0/1 (0.0%) |
| D | mbpp | 0/3 (0.0%) |
| D | team-template | 35/84 (41.7%) |

## Pre-registered targets

Targets of protocol eval-v1 (frozen on 2026-10-21), set from the validation baseline before any test-split run. Rule: Floors (proposal_ready, syntax_valid): lower limit of the two-sided 95% Clopper-Pearson interval of the validation proportion; ceiling (failed): upper limit of that interval; a count that is not determinable under the frozen code uses its least favourable attainable value. Expected direction of a paired comparison: the sign of the validation difference when its Holm-adjusted exact McNemar p < 0.05 for every attainable validation outcome, otherwise none.

| Arm | Measure | Target | Measured | Result |
|---|---|---|---|---|
| A | proposal_ready | >= 2.67% | 7/88 (8.0%) | met |
| A | syntax_valid | >= 93.54% | 87/88 (98.9%) | met |
| A | failed | <= 6.46% | 1/88 (1.1%) | met |
| B | proposal_ready | >= 0.03% | 1/88 (1.1%) | met |
| B | syntax_valid | >= 89.92% | 88/88 (100.0%) | met |
| B | failed | <= 10.08% | 0/88 (0.0%) | met |
| C | proposal_ready | >= 72.26% | 70/88 (79.5%) | met |
| C | syntax_valid | >= 95.70% | 88/88 (100.0%) | met |
| C | failed | <= 4.30% | 0/88 (0.0%) | met |
| D | proposal_ready | >= 43.52% | 35/88 (39.8%) | not met |
| D | syntax_valid | >= 95.70% | 88/88 (100.0%) | met |
| D | failed | <= 4.30% | 0/88 (0.0%) | met |

Expected directions (Holm-adjusted exact McNemar, alpha 0.05):

| Comparison | Expected | Observed | Result |
|---|---|---|---|
| B vs A | none | A accepts more | no direction expected |
| C vs A | C accepts more | C accepts more | confirmed |
| D vs C | C accepts more | C accepts more | confirmed |
| D vs B | D accepts more | D accepts more | confirmed |
