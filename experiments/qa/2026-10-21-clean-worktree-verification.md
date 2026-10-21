# Clean-worktree verification before each push

Before each push of code to `main` on 2026-10-20 and 2026-10-21, the coordinator checked out the exact commit into a separate, detached Git worktree on the demonstration laptop and ran the CI commands there: `uv sync --frozen`, `ruff check .`, `ruff format --check .`, `pytest`, `scripts/check_docs.py` and, when the commit contained the frontend, `npm ci`, `npm run typecheck`, `npm test` and `npm run build` in `frontend/`. The worktree was removed afterwards. This record lists the observed outcomes; the raw console logs were kept outside the repository and are not committed. GitHub Actions then ran the same checks on Ubuntu and Windows for each push.

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
| `911ca3c` | not checked in a worktree | not checked | records only (the test-split evaluation folder); `check_docs.py` in the working tree and GitHub Actions |
| `dd1b0fa` | not checked in a worktree | not checked | report, screenshots and delivery documents only; `check_docs.py` in the working tree and GitHub Actions |
| `90462d3` | 1,550 / 8 | 491 passed, 5 skipped | documentation only; checked after the push in a clean clone from GitHub, where `curate_dataset.py --check` failed on line endings ([clean-clone record](2026-10-21-clean-clone-reproduction.md)) |
| `74daf25` | 1,551 / 8 | not changed | pass, including `curate_dataset.py --check --download` ("reproducible") on a CRLF checkout; fixes the failure found at `90462d3` |

The eight Python skips are the real-GPU provider tests, which run only with `REFACTOR_AI_GPU_TESTS=1`.

## GitHub Actions

Every push to `main` from `d2d2f0b` on triggered the CI workflow, and every run succeeded. The commits after `74daf25` changed documentation, records, the slides and their build scripts only; they were checked with the link checker and ruff before the push and by CI. The `checks` job runs on Ubuntu and Windows; the `frontend` job exists from `5549a77` on. Results were read with `gh run view` on 2026-10-21.

| Commit | Run | Jobs |
|---|---|---|
| `d2d2f0b` | 39402072289 | checks (Ubuntu, Windows) success |
| `5549a77` | 39418314923 | checks (Ubuntu, Windows), frontend success |
| `23c384b` | 39420317310 | checks (Ubuntu, Windows), frontend success |
| `f8dc49c` | 39568128775 | checks (Ubuntu, Windows), frontend success |
| `a546f84` | 39568553218 | checks (Ubuntu, Windows), frontend success |
| `ee87a11` | 39570716794 | checks (Ubuntu, Windows), frontend success |
| `acfa9f1` | 39580972133 | checks (Ubuntu, Windows), frontend success (push of `f187b63` to `acfa9f1`) |
| `6e9751c` | 39582231311 | checks (Ubuntu, Windows), frontend success |
| `c3f0709` | 39582866693 | checks (Ubuntu, Windows), frontend success |
| `9582c66` | 39586231351 | checks (Ubuntu, Windows), frontend success |
| `bad4095` | 39596508027 | checks (Ubuntu, Windows), frontend success |
| `911ca3c` | 39596900308 | checks (Ubuntu, Windows), frontend success |
| `dd1b0fa` | 39598269185 | checks (Ubuntu, Windows), frontend success |
| `90462d3` | 39598461950 | checks (Ubuntu, Windows), frontend success |
| `74daf25` | 39600170341 | checks (Ubuntu, Windows), frontend success |
| `3d761cc` | 39602686994 | checks (Ubuntu, Windows), frontend success |
| `196f4f3` | 39604005416 | checks (Ubuntu, Windows), frontend success |
| `57310a4` | 39604357058 | checks (Ubuntu, Windows), frontend success |
| `6b35e48` | 39604491756 | checks (Ubuntu, Windows), frontend success |

At `74daf25` the Ubuntu job reported 1,550 passed and 9 skipped and the Windows job 1,551 passed and 8 skipped; the extra Ubuntu skip is the Windows-only launcher test in `tests/test_local_provider.py`. The Ubuntu job runs as the unprivileged `runner` user, so from `a546f84` on it also covers the runner tests (`tests/test_runner.py`, `tests/test_runner_child.py`) on Linux after the root-user change; the root path itself is covered by the isolation self-checks in the Kaggle runs.
