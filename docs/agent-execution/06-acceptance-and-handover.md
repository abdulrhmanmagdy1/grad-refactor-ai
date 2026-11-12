# 06 — Acceptance and handover

Completion checklist for the coding agent and the team's final inspection. A checkbox is ticked
only with a linked, verifiable artifact — never on assumption.

## Requirement acceptance

| Requirement | Evidence required | Status |
|---|---|---|
| FR01 Bounded input | 422 tests for blank/oversized/malformed input | ☐ |
| FR02 Analyze code | Structured findings with location + reason; async + nesting rules | ☐ |
| FR03 Propose refactoring | Code + reason + supported type, or explicit failure | ☐ |
| FR04 Verify proposal | Syntax, tests and verdict shown separately | ☐ |
| FR05 Show diff | Added/removed lines and affected components | ☐ |
| FR06 User control | Accept/reject/download without editing the original | ☐ |
| FR07 Trace each run | id, config/limits, model version, state, durations, failures | ☐ |
| FR08 Bound execution | Enforced call/retry/token/time limits with clear failure | ☐ |
| FR09 Compare experiments | Groups A/B/C/D on the same cases with CSV + JSON export | ☐ |
| FR10 Run history | Previous results retrievable on the demonstration machine | ☐ |
| NFR01 No code execution in API | AST-only analysis; file-write probe test passes | ☐ |
| NFR02 Isolated runner | CPU/mem/time limits, sanitized env, cleanup, trusted examples | ☐ |
| NFR03 No paid services | Core runs with no API key or committed credentials | ☐ |
| NFR04 Pinned core env | Python 3.11 + lockfile; GPU deps resolved separately | ☐ |
| NFR05 Experiment record completeness | run-template fields populated from real runs | ☐ |
| NFR06 No false equivalence claim | Tests never presented as full behavioral proof | ☐ |
| NFR07 Measured targets | Response-time/memory targets set from measurement | ☐ |

## Delivery checklist

- [ ] Clean clone + fresh environment run reproduced (state whether a second machine was used).
- [ ] Data licensing, curation, independent splits and versions recorded.
- [ ] Fine-tuning settings + reloadable adapter recorded within storage/license limits (or a
      recorded blocker, with the base model never reported as trained).
- [ ] Original vs adapted model and single-role vs coordinated workflow compared.
- [ ] Failures, resource use and limitations included in the evaluation.
- [ ] Developer guide, user guide and model card updated.
- [ ] Academic report written to the university template (problem, related work, method, design,
      implementation, experiments, results, limitations, future work).
- [ ] Presentation, repeatable demo and a small backup recording prepared.
- [ ] Release tagged with notes, checksums and experiment links.
- [ ] P5 review recorded and follow-up priorities set.

## Final team inspection

- [ ] Reproduce the demo from the repository instructions alone.
- [ ] Confirm no result, approval or citation was invented.
- [ ] Confirm the trust boundary held (no untrusted execution in the API).
- [ ] Confirm each follow-up task has one accountable owner from
      [`planning/assignments.json`](../../planning/assignments.json).

Use [`docs/delivery/checklist.md`](../delivery/checklist.md) as the team-facing companion to this
document. A phase ending does not automatically complete its tasks.
