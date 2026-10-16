# Project risks

| Risk | Early signal | Response | Responsible role |
|---|---|---|---|
| No suitable GPU | Training smoke test fails in P1 | Reduce model, context, or task; discuss university resources | Coordinator and training owner |
| Interrupted free compute | Sessions terminate | Record checkpoints and recovery; keep demonstration hosting independent | Training owner |
| Weak data | Invalid changes or unclear licenses | Review samples, reference tests, and source suitability | Data owner |
| Data leakage | Related projects or examples cross splits | Split by source and check near-duplicates | Evaluation owner |
| Fine-tuning regression | Validation is worse than baseline | Review data and settings; retain and report the baseline | Training owner |
| Late integration | No full case by Day 10 | Prioritize one complete path and defer extras | Integration owner |
| Scope growth | More languages or roles without evidence | Enforce the agreed release scope | Team |
| Unsafe execution | Untrusted code reaches execution | Keep execution disabled until runner review; use trusted MVP examples | API and verification owners |
| Delayed supervisor review | No appointment before phase end | Arrange early; prepare written evidence; continue independent work | Coordinator |
| GitHub quota limits | Artifacts exceed the free allowance | Check early; prefer small adapters and manifests | Coordinator |
| Incomplete team access | A member cannot open the repo or board | Verify both permissions and invitation acceptance | Repository owner |
