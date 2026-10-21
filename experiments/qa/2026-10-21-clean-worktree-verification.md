# Clean-worktree verification before each push

Before each push to `main` on 2026-10-20 and 2026-10-21, the coordinator checked out the exact commit into a separate, detached Git worktree on the demonstration laptop and ran the CI commands there: `uv sync --frozen`, `ruff check .`, `ruff format --check .`, `pytest`, `scripts/check_docs.py` and, when the commit contained the frontend, `npm ci`, `npm run typecheck`, `npm test` and `npm run build` in `frontend/`. The worktree was removed afterwards. This record lists the observed outcomes; the raw console logs were kept outside the repository and are not committed. GitHub Actions then ran the same checks on Ubuntu and Windows for each push.

| Commit | Python tests (passed / skipped) | Frontend tests | Outcome |
|---|---|---|---|
| `d2d2f0b` | 43 / 0 | not present | pass |
| `f282276` | 971 / 0 | not present | pass |
| `d377723` | 1,240 / 1 | not present | pass; the first attempt of this change, committed before `f282276`, failed 3 tests because it needed the verification package, so the commits were reordered |
| `5549a77` | 1,240 / 1 | typecheck, tests and build pass | pass |
| `446db35` | 1,298 / 2 | not changed | pass after an amendment; the first attempt failed `ruff check` (isort treated the new `datasets/` directory as a first-party package), fixed by `known-third-party = ["datasets"]` |
| `23c384b` | 1,364 / 8 | not checked | pass |
| `f8dc49c` | 1,425 / 8 | pass | pass |
| `a546f84` | 1,426 / 8 | not checked | pass |
| `ee87a11` | 1,426 / 8 | pass | pass |
| `3ffb16f` | 1,500 / 8 | 1 failed of 493 | fail: the interface test "has a text for every task reason code" lacked a label for the new `too_complex` code; fixed by `acfa9f1` before either commit was pushed |
| `acfa9f1` | 1,500 / 8 | 488 passed, 5 skipped | pass; `f187b63` to `acfa9f1` were pushed together |
| `6e9751c` | 1,500 / 8 | not checked | pass |
| `c3f0709` | 1,520 / 8 | not checked | pass |
| `9582c66` | 1,550 / 8 | not checked | pass (includes the frozen-code test of protocol eval-v1) |
| `bad4095` | 1,550 / 8 | 491 passed, 5 skipped | pass |

The eight Python skips are the real-GPU provider tests, which run only with `REFACTOR_AI_GPU_TESTS=1`. GitHub Actions results for the pushes of `d2d2f0b`, `5549a77` and `23c384b` (runs 39402072289, 39418314923 and 39420317310) were successful on Ubuntu and Windows, and from `5549a77` on also for the frontend job.
