# Demonstration script

Status: prepared on 2026-10-21 by a coding agent for Dania El-Walily (T27, presentation and repeatable demonstration), and updated the same day after a dry run. The team has not rehearsed it. In the dry run the coordinating agent submitted every demonstration case once in each workflow to the service with the fine-tuned model on the demonstration laptop ([dry-run record](../../experiments/integration/2026-10-21-demo-dry-run.json)); its results fill the table below, but the timings of a spoken rehearsal are still unknown. Commands are for Windows PowerShell on the demonstration laptop and are run from the repository root. The [user guide](user-guide.md) explains every screen and setting in full, and the [slides](slides/grad-refactor-ai-presentation.pptx) carry the matching demonstration slide.

## What the audience must see

In 8 to 10 minutes, with the fine-tuned model, the audience sees:

- a run that succeeds ("Ready to use");
- an input outside the task ("Nothing to change", with no model call);
- a refused submission (invalid syntax) and a run that cannot be fully checked ("Not sure", because no trusted tests exist for edited code).

Along the way, point at:

- the status pill in the header and its details (model identity, adapter, runner);
- the four check chips (Valid Python, Guard clauses, Tests, Review), which are never merged into one verdict;
- the diff;
- the run record under Details.

Never present a demo-mode (fake provider) result as model output. The roles during the session:

| Role | Person | Task |
|---|---|---|
| Driver and narrator | Dania El-Walily | Runs the interface and speaks the script |
| Backup operator | Abdelrahman Magdy | Watches the service window and switches to a backup if needed |
| Questions on the checks | Abdullah Tarek | Rubric, reference tests, model review, correction |
| Questions on the model | Abdelrahman Adel | Model identity, adapter, speed, memory |

## Before the day: rehearsal (about 45 minutes)

1. **Check the configuration.** The validation-only selection adopted the LoRA adapter for the refactoring role ([selection record](../../experiments/training/validation-selection-2026-10-20.json)); the analysis and review roles always use the base model. `configs/model.local.json` is not in Git: it must name the adapter directory, id `full-2026-10-21` and the checksums in the [model card](../data-and-training/model-card.md). The models workstream supplies the file and the adapter folder.
2. **Check the machine.** Close GPU-heavy programs and browser tabs you do not need. No training or evaluation job may use the GPU during the demonstration. Run:

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

3. **Start the service with the fine-tuned model** and its own run history, so that development runs do not appear:

   ```powershell
   $env:REFACTOR_AI_PROVIDER = "local"
   $env:REFACTOR_AI_REFACTOR_USE_ADAPTER = "true"
   $env:REFACTOR_AI_DB = "runs/demo/runs.sqlite3"
   python -m uv run uvicorn refactor_ai.api:app --host 127.0.0.1 --port 8000
   ```

4. **Wait until the service is ready.** In a second PowerShell window:

   ```powershell
   $h = Invoke-RestMethod http://127.0.0.1:8000/health
   "{0} ready={1} model={2}@{3} adapter={4} use_adapter={5} runner={6}" -f $h.mode, $h.provider.ready, $h.provider.model_id, $h.provider.model_revision, $h.provider.adapter_id, $h.refactor_use_adapter, $h.runner.enabled
   ```

   Expect `local_model ready=True model=Qwen/Qwen2.5-Coder-0.5B-Instruct@ea3f2471cf1b1f0db85067f1ef93848e38e88c25 adapter=full-2026-10-21 use_adapter=True runner=True`. Repeat the command until `ready=True`. With the adapter, the model loaded in 33.2 s before the dry run; the runner's isolation self-checks take about 5 to 10 s after startup.

5. **Open the interface** with `Start-Process http://127.0.0.1:8000/`. The status pill must read "Fine-tuned model ready".
6. **Run the cases you will show** and compare them with the dry run below. Greedy decoding gave the same output for the same input in the model benchmark, so the same commit, configuration and case is expected to give the same outcome on the day. That is expected, not guaranteed: if an outcome differs, show what happened and say so.
7. **Time the spoken script** with a stopwatch and adjust the segment times.
8. **Record a short backup video** of the whole script, and keep the rehearsal database (`runs/demo/`): its runs are the first fallback on the day.

### Dry run of 2026-10-21

Every run below used the fine-tuned adapter for the refactoring call and the service defaults, which allow the review more tokens than the evaluation did. The cases are the six server-owned demonstration cases, not test cases, so this is no measure of quality.

| Case | Fast: outcome | Fast: tests | Fast: time | With review: outcome | With review: tests, review | With review: time |
|---|---|---|---|---|---|---|
| `demo-library-fine` | Ready to use | 6/6 | 19 s | Ready to use | 6/6, accept | 23 s |
| `demo-print-job` | Ready to use | 8/8 | 22 s | Ready to use | 8/8, accept | 31 s |
| `demo-wifi-signal` | Ready to use | 11/11 | 25 s | Ready to use | 11/11, accept | 34 s |
| `demo-port-number` | Ready to use | 11/11 | 20 s | Ready to use | 11/11, accept | 30 s |
| `demo-recycling-points` | Ready to use | 6/6 | 26 s | Ready to use | 6/6, accept | 36 s |
| `demo-dice-score` | Ready to use | 10/10 | 29 s | Ready to use | 10/10, accept | 43 s |
| `sign` (below) | | | | Nothing to change (`no_opportunity`), 0 model calls | not run | under 1 s |

With review, every run made 3 model calls and needed no correction. The times include polling and are wall-clock times on the laptop. Use `demo-library-fine` (10 lines, 6 tests) for the success segment: it is the shortest case and the fastest run.

## On the day: setup (before the audience, about 5 minutes)

Repeat steps 2 to 5 with the same commit, configuration and database. Leave the interface open on the empty input. Start the timer only when the audience is ready.

## The script (9 minutes 30 seconds, including 30 seconds of buffer)

| Time | Segment | Outcome shown |
|---|---|---|
| 0:00-1:00 | Orientation | Fine-tuned model, identity, runner enabled |
| 1:00-4:30 | Success | Ready to use, chips, diff, run record |
| 4:30-5:30 | Unsupported input | Nothing to change, zero model calls |
| 5:30-8:00 | What the checks refuse | Invalid syntax; edited case ends Not sure |
| 8:00-9:00 | User control | Download, decision, history |
| 9:00-9:30 | Close | What the demonstration does and does not show |

If time runs short, skip the side-by-side view in the success segment and the history in the user-control segment. That saves about one minute.

### 0:00-1:00 Orientation

Select the status pill "Fine-tuned model ready" in the header and point at its details, item by item:

- **Provider:** "AI model".
- **Model:** model id, revision and device.
- **Refactoring role:** "Fine-tuned LoRA adapter", the adapter id and the start of its checksum, and "Analysis and review use the base model."
- **Model status:** "Ready".
- **Reference tests:** "Runner enabled".
- **Queue.**

Say: "There is no amber banner, so this is the real model. In demo mode a banner stays at the top of every screen and says 'Demo mode: results come from a test stub, not the AI model.'" Then one sentence on the task: one small Python function, one refactoring, flattening nested if statements into guard clauses.

### 1:00-4:30 Success

1. Under **Demonstration case**, choose "Library fine" and select **Load case**. Point at the notice "6 tests will run": the code is linked to a server-owned case, and its trusted reference tests will run.
2. Keep **With review (default)** and select **Improve code**. (With **Fast** the run is quicker and skips the review; both ended "Ready to use" in the dry run.)
3. While it runs, point at the stepper (Queued, Find, Rewrite, Check and review) and the elapsed time. Say: "One local model plays three roles through three separate prompts: find, rewrite and review. A run makes at most five calls and at most one correction."
4. **Verdict:** "Ready to use. All checks passed. Read the change before you accept it."
5. **Check chips:** Valid Python "Passed", Guard clauses "Passed", Tests "6/6 passed", Review "Accepted". Say: "Each check is shown on its own. The tests ran in a separate, limited process, and they cover these inputs only: tests check examples, not every possible input."
6. **Proposed change:** the unified diff. Optionally switch to **Side by side**. Say that the application computes the diff from the two texts; the model does not write it.
7. **Details:** open it and point at "Verification" (the eight rubric checks, the test count), the model's "Explanation" (written by the model and not checked; read the diff, not the explanation) and the "Run record": the exact model identity, whether the adapter was active, the model calls against their limit, the timings and the raw output of each attempt.

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

Select **Improve code**. The verdict is "Nothing to change" with reason `no_opportunity`: the function is already flat. The run record shows zero model calls and stop reason `unsupported_input`. Say: "The scope is checked before any model call, so out-of-scope input costs nothing and can never be 'refactored' by accident." If you have extra time, a function that calls `print` ends with `denied_call:print`.

### 5:30-8:00 What the checks refuse

1. **Invalid input (deterministic, 30 seconds).** Paste the code below and select **Improve code**. The submission is refused before any run starts: "The code is not valid Python", line 1, column 14, and **Go to line 1** selects the line. Nothing was executed and no run was created.

   ```python
   def broken(x)
       return x
   ```

2. **Edited case.** Load "Library fine" again and change one letter in the docstring. The notice says that the tests of the case will not run. Select **Improve code**. Without trusted tests the best possible verdict is "Not sure": the Tests chip shows "No tests", and the reason is `tests_not_available`. Say: "Missing tests never count as a pass."
3. **Rejections in the evaluation.** None of the six demonstration cases was rejected in the dry run. Point back to the results slide: on the frozen test split the fine-tuned model was rejected in 18 of 88 cases, because reference tests failed. Say: "When that happens, the verdict is 'Not safe to use', the failing tests are listed under Details, and the review cannot turn a failed check into a pass."

### 8:00-9:00 User control

Open the success run from **History** and select **Download proposal**: the file is `proposal-<run id>.py`. Then select **Accept proposal**, and point at "Decision recorded: accepted." Say: "The decision is only a record. The service never edits the user's files or the code in the editor."

### 9:00-9:30 Close

Say: "This shows the system working on the demonstration laptop. The evidence that fine-tuning helps comes from the frozen test split on the slides, not from these runs." Then return to the slides.

## Backup plan

Use the first backup that works. Always say aloud which one you are using.

| Problem | Backup |
|---|---|
| A live run is slow | Keep narrating from the stepper. After 2 minutes, open the same case's rehearsal run from **History**. Say: "This is the run recorded during the rehearsal at <time>." The run record shows the provider and model identity. |
| The model does not load, or fails | Read the reason in the status pill details or in `/health`. Open the rehearsal runs from **History**; they are real runs with the model, recorded in `runs/demo/`. |
| The service does not start | "Address already in use": add `--port 8001` and open that port. "The run database ... is already in use by another service process": stop the other service, or set another `REFACTOR_AI_DB`. An invalid setting: the message names the variable. |
| The adapter is missing | The pill shows "Adapter missing", the details show "Adapter requested, none configured", and every run fails with `adapter_unavailable` before any model call. Either fix `configs/model.local.json`, or restart without `REFACTOR_AI_REFACTOR_USE_ADAPTER` and say that the base model is shown (the pill then reads "Base model ready"). |
| The interface fails but the service works | Use the API from PowerShell as in the [user guide](user-guide.md#example-session-in-powershell). |
| No GPU or no time to recover | Demo mode, clearly labeled (next section). |
| The laptop fails | The slides (PDF copy in [slides/](slides/grad-refactor-ai-presentation.pdf)), the screenshots and the backup recording (below). |

### Demo mode, clearly labeled

Stop the service with Ctrl+C, then start it in the same window:

```powershell
Remove-Item Env:REFACTOR_AI_PROVIDER
Remove-Item Env:REFACTOR_AI_REFACTOR_USE_ADAPTER -ErrorAction SilentlyContinue
$env:REFACTOR_AI_DB = "runs/demo-fake/runs.sqlite3"
python -m uv run uvicorn refactor_ai.api:app --host 127.0.0.1 --port 8000
```

Remove the adapter switch: with it, every demo-mode run fails with `adapter_unavailable`. Before the first run, say: "This is demo mode. It applies the deterministic reference transformation and a placeholder review. It shows how the interface and the checks work, and nothing about the model." The amber banner stays on screen, the pill reads "Demo mode", runs in the history carry a "Fake" tag, and the Review chip shows "Demo only". Do not hide or crop any of these.

### Screenshots

The screenshots in `docs/report/screenshots/` were taken on 2026-10-21 from the simplified interface (commit `bad4095`) served on the demonstration laptop with the fine-tuned model (adapter `full-2026-10-21`, bf16) and the real reference runner, at 1440 by 900 px and 390 by 844 px. They show single real runs, so present each as one example, not as a measured rate. None shows a "Not safe to use" verdict or a failed run.

| Script step | Screenshot |
|---|---|
| Orientation | [s01-empty-light.png](../report/screenshots/s01-empty-light.png) |
| Case loaded and linked | [s02-case-loaded-light.png](../report/screenshots/s02-case-loaded-light.png) |
| Run in progress | [s04-run-in-progress-light.png](../report/screenshots/s04-run-in-progress-light.png) |
| Verdict and chips | [s05-proposal-ready-light.png](../report/screenshots/s05-proposal-ready-light.png) |
| Diff and decision | [s05b-diff-and-verification-light.png](../report/screenshots/s05b-diff-and-verification-light.png) |
| Run record | [s05c-run-record-light.png](../report/screenshots/s05c-run-record-light.png) |
| Side by side | [s06-side-by-side-light.png](../report/screenshots/s06-side-by-side-light.png) |
| Unsupported input | [s08-no-change-light.png](../report/screenshots/s08-no-change-light.png) |
| Invalid syntax | [s09-invalid-syntax-light.png](../report/screenshots/s09-invalid-syntax-light.png) |
| Link removed, Not sure | [s03-link-removed-light.png](../report/screenshots/s03-link-removed-light.png), [s07b-uncertain-verification-light.png](../report/screenshots/s07b-uncertain-verification-light.png) |
| Decision recorded | [s12-decision-recorded-light.png](../report/screenshots/s12-decision-recorded-light.png) |
| History | [s13-history-delete-light.png](../report/screenshots/s13-history-delete-light.png) |

### Backup recording

The [delivery checklist](checklist.md) asks for a small backup recording. Record it during the rehearsal (step 8), name the commit and the configuration at its start, and store it outside Git unless its size and contents are checked first. It does not exist yet.

## Rules

- Say which mode is running before the first run. Never present demo-mode output as model output.
- Never claim that passing reference tests proves identical behavior. They cover the trusted inputs only.
- Never claim reference tests ran for edited or pasted code. They run only for an unchanged demonstration case.
- Do not run training, evaluation or other GPU work on the laptop during the demonstration.
- Afterwards, record the commit, mode, configuration, cases, run ids and outcomes in the review pack of the meeting where the demonstration was shown.
