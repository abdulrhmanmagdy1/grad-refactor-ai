# Demonstration script

Status: prepared on 2026-10-21 by a coding agent for Dania El-Walily (T27, presentation and repeatable demonstration). It has not been rehearsed. No timing below was measured in a rehearsal, and nobody knows yet which demonstration case the local model handles well. The rehearsal fills in the case choices and the table below. Commands are for Windows PowerShell on the demonstration laptop and are run from the repository root. The [user guide](user-guide.md) explains every screen and setting in full.

## What the audience must see

In 8 to 10 minutes, with the local model, the audience sees:

- a run that succeeds;
- an input outside the task (`no_change`, with no model call);
- a run whose proposal fails a check, or a failed run.

Along the way, point at:

- the model identity and the fake-or-real mode in the header;
- the diff;
- the four verification results (Syntax, Task rubric, Reference tests, Model review), which are never merged into one verdict;
- the run record.

Never present a fake-provider result as model output. The roles during the session:

| Role | Person | Task |
|---|---|---|
| Driver and narrator | Dania El-Walily | Runs the interface and speaks the script |
| Backup operator | Abdelrahman Magdy | Watches the service window and switches to a backup if needed |
| Questions on the checks | Abdullah Tarek | Rubric, reference tests, model review, correction |
| Questions on the model | Abdelrahman Adel | Model identity, adapter, speed, memory |

## Before the day: rehearsal (about 45 minutes)

1. **Fix the configuration.** Show the configuration chosen by the validation-only selection, T22: the base model, or the LoRA adapter on the refactoring role ([R4 review pack](../supervisor-reviews/r4-first-release.md), question 3). With the adapter, `configs/model.local.json` must name the adapter directory, id and checksum supplied by the models workstream. The analysis and review roles always use the base model.
2. **Check the machine.** Close GPU-heavy programs and browser tabs you do not need. Nothing else may use the GPU: no training or evaluation job runs on the laptop during the demonstration. Run:

   ```powershell
   git rev-parse --short HEAD
   git status --short
   python -m uv run python scripts/doctor.py
   nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv
   Test-Path configs\model.local.json
   Test-Path frontend\dist\index.html
   ```

   Note the commit: it goes into the review record. `Test-Path` must print `True` twice. If the interface build is missing or older than the last frontend change, build it:

   ```powershell
   cd frontend
   npm ci
   npm run build
   cd ..
   ```

3. **Start the service in local-model mode** with its own run history, so that development runs do not appear:

   ```powershell
   $env:REFACTOR_AI_PROVIDER = "local"
   $env:REFACTOR_AI_DB = "runs/demo/runs.sqlite3"
   # Only if T22 selected the adapter:
   # $env:REFACTOR_AI_REFACTOR_USE_ADAPTER = "true"
   python -m uv run uvicorn refactor_ai.api:app --host 127.0.0.1 --port 8000
   ```

4. **Wait until the service is ready.** In a second PowerShell window:

   ```powershell
   $h = Invoke-RestMethod http://127.0.0.1:8000/health
   "{0} ready={1} model={2}@{3} adapter={4} use_adapter={5} runner={6}" -f $h.mode, $h.provider.ready, $h.provider.model_id, $h.provider.model_revision, $h.provider.adapter_id, $h.refactor_use_adapter, $h.runner.enabled
   ```

   Expect `local_model ready=True model=Qwen/Qwen2.5-Coder-0.5B-Instruct@ea3f2471cf1b1f0db85067f1ef93848e38e88c25` and `runner=True`. With the adapter, `adapter` must show its id and `use_adapter=True`. Repeat the command until `ready=True`. The measured model load took 17.6 s with a warm file cache and 88.1 s cold ([model records](../../experiments/models/README.md)). The runner's isolation self-checks take about 5 to 10 s after startup.

5. **Open the interface** with `Start-Process http://127.0.0.1:8000/`.
6. **Run every demonstration case once** in Multi-role, in the chosen configuration, and fill in the table. Then pick the cases:
   - **Success case:** a case that ended `proposal_ready`. Prefer a short one; `demo-library-fine` has 10 lines and 6 tests.
   - **Failure case:** a case that ended `rejected`, or `failed`.

   In the 24-record prompt study the base model returned 14 inputs unchanged ([selection record](../../experiments/models/2026-10-20-prompt-format-selection.md)). An unchanged copy passes the reference tests but fails the rubric check "Reduces the nesting depth", so a `rejected` outcome is likely among the six cases with the base model. Greedy decoding gave byte-identical outputs across repeated runs in the model benchmark, so the same commit, configuration and case is expected to give the same outcome on the day. That is expected, not guaranteed: if the outcome differs, show what happened and say so.
7. **Time the runs.** A multi-role run makes 3 model calls, or 5 with a correction. In the prompt study a refactoring call took 5.09 s at the median and 10.60 s at most on this laptop. Record the measured duration of each case below, and adjust the timings in the script.
8. **Capture local-model screenshots** of the header, the success outcome and the failed check, and record a short backup video of the whole script. Hand both to the frontend workstream for `docs/report/screenshots/`, together with the commit and the configuration.
9. **Keep the rehearsal database** (`runs/demo/`). Its runs are the first fallback on the day.

| Case | Workflow | Refactoring role weights | Disposition | Stop reason | Calls | Duration | Run id | Recorded at |
|---|---|---|---|---|---|---|---|---|
| `demo-library-fine` | Multi-role | | | | | | | |
| `demo-print-job` | Multi-role | | | | | | | |
| `demo-wifi-signal` | Multi-role | | | | | | | |
| `demo-port-number` | Multi-role | | | | | | | |
| `demo-recycling-points` | Multi-role | | | | | | | |
| `demo-dice-score` | Multi-role | | | | | | | |
| `sign` (unsupported input) | Multi-role | | `no_change` expected | `unsupported_input` expected | 0 expected | | | |

**If no case ends `proposal_ready`.** Do not switch to fake mode to obtain a success. Decide with the coordinator before the presentation, and tell the examiners which option you chose:

- show the best real outcome and explain it, which matches the validation evidence for a 0.5B model; or
- walk through the success screens in fake mode, clearly labelled as the deterministic reference transformation, followed by the real outcomes.

## On the day: setup (before the audience, about 5 minutes)

Repeat steps 2 to 5 with the same commit, configuration and database. Leave the interface open on the empty input. Start the timer only when the audience is ready.

## The script (9 minutes 30 seconds, including 30 seconds of buffer)

| Time | Segment | Outcome shown |
|---|---|---|
| 0:00-1:00 | Orientation | Local model, identity, runner enabled |
| 1:00-4:30 | Success | `proposal_ready`, diff, four results, run record |
| 4:30-5:30 | Unsupported input | `no_change`, zero model calls |
| 5:30-8:00 | Failed or rejected check | `rejected` (or `failed`), plus invalid syntax |
| 8:00-9:00 | User control | Download, decision, history |
| 9:00-9:30 | Close | What the demonstration does and does not show |

If time runs short, skip the side-by-side view in segment 1 and the history in segment 4. That saves about one minute.

### 0:00-1:00 Orientation

Point at the header, item by item:

- **Provider:** "Local model".
- **Model:** model id, revision and device.
- **Refactoring role:** "Base model", or "Fine-tuned LoRA adapter" with the adapter id and the start of its checksum.
- **Model status:** "Ready".
- **Reference tests:** "Runner enabled".
- **Queue.**

Say: "There is no amber banner, so this is the real model. In fake mode a banner stays at the top of every screen and says 'Fake provider: these are not language-model results.'" Then one sentence on the task: one small Python function, one refactoring, replacing nested conditionals with guard clauses.

### 1:00-4:30 Success

1. Under **Demonstration case**, choose the success case from the rehearsal and select **Load case**. Point at the notice: the code is linked to a server-owned case, and its trusted reference tests will run.
2. Keep the workflow on **Multi-role (default)** and select **Propose refactoring**.
3. While it runs, point at the stepper (Queued, Analysis, Refactoring, Verification) and the elapsed time. Say: "One local model plays three roles through three separate prompts: analysis, refactoring and review. A run makes at most five calls and at most one correction."
4. **Outcome:** "Proposal ready for your review", the reasons given by the service, and the indentation outline of the original and the proposal. The outline is a display aid; the rubric gives the verdict.
5. **Proposed change:** the unified diff. Optionally switch the diff layout to **Side by side**, which highlights the lines flagged by the analysis. Say that the application computes the diff from the two texts; the model does not write it.
6. **Verification:** point at the four separate results:
   - **Syntax:** the proposal parses; Python's parser only, nothing executed.
   - **Task rubric:** the eight structural checks, including "Reduces the nesting depth" and "Introduces no new calls".
   - **Reference tests:** "N of N tests passed", with the note "Passed for these trusted inputs only. This is not proof of identical behavior for every input." They ran in a separate, limited process.
   - **Model review:** the verdict, with the note "A model verdict is not proof of correctness and never overrides a failed check."
7. **Run record:** the exact model identity, including whether the adapter was active for the refactoring call. Also point at the calls against their limit, the stage timings, the raw model output of each attempt and the stop reason.

### 4:30-5:30 Unsupported input

Clear the editor and paste:

```python
def sign(x):
    if x > 0:
        return 1
    elif x < 0:
        return -1
    return 0
```

Select **Propose refactoring**. The result is "No change proposed" with reason `no_opportunity`: the function is already flat. The run record shows zero model calls and stop reason `unsupported_input`. Say: "The scope is checked deterministically before any model call, so out-of-scope input costs nothing and can never be 'refactored' by accident." The outcome does not depend on the model. If you have extra time, a function that calls `print` ends with `denied_call:print`.

### 5:30-8:00 Failed or rejected check

1. Load the failure case from the rehearsal and select **Propose refactoring** in the same workflow.
2. **Outcome:** "Proposal rejected by verification", with the reason codes, for example `rubric_fail` or `tests_fail`.
3. **Verification:** point at the check that failed. For an unchanged copy this is the rubric check "Reduces the nesting depth". For a behavior change it is the reference-test table (Test index, Problem, Detail). Say: "The other results stay visible and separate. The model's review cannot turn a failed check into a pass."
4. If the run used the correction, point at "Refactoring (correction)" in the stepper and at the two attempts in the run record. Say that the correction prompt shows up to three failing reference tests to the model. That is oracle feedback, which the evaluation reports.
5. **Invalid input (deterministic, 30 seconds).** Paste the code below and propose. The submission is refused before any run starts: `invalid_syntax` at line 1, column 14, and **Go to line** selects the line. Nothing was executed and no run was created.

   ```python
   def broken(x)
       return x
   ```

6. **Optional, if time allows.** Load any case and change one character. The link to the case is removed with a notice. The run's reference tests are then `not_available`, so its best possible outcome is `uncertain` (`tests_not_available`), never `proposal_ready`: missing tests never count as a pass.

### 8:00-9:00 User control

Open the success run from **History** and select **Download proposal**: the file is `proposal-<run id>.py`. Then select **Accept proposal**, and point at "Decision recorded: accepted." Say: "The decision is only a record. The service never edits the user's files or the code in the editor."

### 9:00-9:30 Close

Say: "This shows the system working on the demonstration laptop. It does not show that fine-tuning or the multi-role workflow is better. That answer comes from the evaluation on the frozen test split." Then return to the slides.

## Backup plan

Use the first backup that works. Always say aloud which one you are using.

| Problem | Backup |
|---|---|
| A live run is slow | Keep narrating from the stepper. After 2 minutes, open the same case's rehearsal run from **History**. Say: "This is the local-model run recorded during the rehearsal at <time>." The run record shows the provider and model identity. |
| The model does not load, or fails | Read the reason in the header (Model status) or in `/health`. Open the rehearsal runs from **History**. They are real local-model runs, recorded in `runs/demo/`. |
| The service does not start | "Address already in use": add `--port 8001` and open that port. "The run database ... is already in use by another service process": stop the other service, or set another `REFACTOR_AI_DB`. An invalid setting: the message names the variable. |
| The adapter is missing | The header shows "Adapter requested, none configured" and Model status "Adapter missing", and every run fails with `adapter_unavailable` before any model call. Either fix `configs/model.local.json`, or restart without `REFACTOR_AI_REFACTOR_USE_ADAPTER` and say that the base model is shown. |
| The interface fails but the service works | Use the API from PowerShell as in the [user guide](user-guide.md#example-session-in-powershell). |
| No GPU or no time to recover | Fake mode, clearly labelled (next section). |
| The laptop fails | Screenshots and the backup recording (below). |

### Fake mode, clearly labelled

Stop the service with Ctrl+C, then start it in the same window:

```powershell
Remove-Item Env:REFACTOR_AI_PROVIDER
Remove-Item Env:REFACTOR_AI_REFACTOR_USE_ADAPTER -ErrorAction SilentlyContinue
$env:REFACTOR_AI_DB = "runs/demo-fake/runs.sqlite3"
python -m uv run uvicorn refactor_ai.api:app --host 127.0.0.1 --port 8000
```

Remove the adapter switch: with it, every fake-mode run fails with `adapter_unavailable`. Before the first run, say: "This is the fake provider. It applies the deterministic reference transformation and a placeholder review. It shows how the interface and the checks work, and nothing about the model." The amber banner stays on screen, the header shows "Fake provider (test only)", the outcome is tagged "Fake provider output", and the model review is drawn as a placeholder. Do not hide or crop any of these.

### Screenshots

The screenshots in `docs/report/screenshots/` were taken on 2026-10-21 from the simplified interface (commit `bad4095`) served on the demonstration laptop with the fine-tuned model (adapter `full-2026-10-21`, bf16) and the real reference runner, at 1440 by 900 px and 390 by 844 px. They show real model output from single runs, so present each as one example, not as a measured rate. None shows a `rejected` outcome or a failed run. Add the local-model screenshots from the rehearsal when they exist.

| Script step | Screenshot |
|---|---|
| Orientation (header with the model status) | [s01-empty-light.png](../report/screenshots/s01-empty-light.png) |
| Case loaded and linked | [s02-case-loaded-light.png](../report/screenshots/s02-case-loaded-light.png) |
| Run in progress | [s04-run-in-progress-light.png](../report/screenshots/s04-run-in-progress-light.png) |
| Outcome | [s05-proposal-ready-light.png](../report/screenshots/s05-proposal-ready-light.png) |
| Diff and verification | [s05b-diff-and-verification-light.png](../report/screenshots/s05b-diff-and-verification-light.png) |
| Run record | [s05c-run-record-light.png](../report/screenshots/s05c-run-record-light.png) |
| Side by side | [s06-side-by-side-light.png](../report/screenshots/s06-side-by-side-light.png) |
| Unsupported input | [s08-no-change-light.png](../report/screenshots/s08-no-change-light.png) |
| Invalid syntax | [s09-invalid-syntax-light.png](../report/screenshots/s09-invalid-syntax-light.png) |
| Link removed, `uncertain` | [s03-link-removed-light.png](../report/screenshots/s03-link-removed-light.png), [s07b-uncertain-verification-light.png](../report/screenshots/s07b-uncertain-verification-light.png) |
| Decision recorded | [s12-decision-recorded-light.png](../report/screenshots/s12-decision-recorded-light.png) |
| History | [s13-history-delete-light.png](../report/screenshots/s13-history-delete-light.png) |

### Backup recording

The [delivery checklist](checklist.md) asks for a small backup recording. Record it during the rehearsal (step 8), name the commit and the configuration at its start, and store it outside Git unless its size and contents are checked first. It did not exist at preparation.

## Rules

- Say which mode is running before the first run. Never present fake-provider output as model output.
- Never claim that passing reference tests proves identical behavior. They cover the trusted inputs only.
- Never claim reference tests ran for edited or pasted code. They run only for an unchanged demonstration case.
- Do not run training, evaluation or other GPU work on the laptop during the demonstration.
- Afterwards, record the commit, mode, configuration, cases, run ids and outcomes in the review pack of the meeting where the demonstration was shown.
