# Frontend notes

Workstream: frontend and delivery (owner Dania El-Walily). Tasks: T16, the code-input and result interface, and the interface half of T21, verification and failure results. Written on 2026-10-20 from the implementation and its tests, and updated the same day for the second wave of contract changes (the refactoring role's weights in `/health`, new per-role generation limits, the `adapter_unavailable` run error and the `correction_input_too_long` stop reason). Every run shown in the interface during development came from the deterministic fake provider, so nothing here is evidence of model behavior. Setup and commands are in the [frontend development guide](../../development/frontend.md).

## What the interface does

A local single-page application lets a person paste one Python function, or load a demonstration case, and ask the service for a guard-clause refactoring. It follows the run while it is queued, analyzed, generated and verified, then shows the outcome, a diff, the four verification results, the explanation and findings, and the run record. The person can copy or download the proposal and record an accept or reject decision. The header shows the provider, the exact model identity, which weights the refactoring role uses (the fine-tuned LoRA adapter or the base model; analysis and review always use the base model) and, when the model cannot serve runs, why: still loading, a requested adapter that is missing, or another reason given by the service. Earlier runs can be reopened or deleted from the history. The service's API and records are described in the [contracts](../../architecture/contracts.md) and the [backend notes](backend.md).

| Requirement | How the interface meets it |
|---|---|
| FR01 bounded input | Counts characters as Python does (code points) against the 20,000-character limit and blocks submission above it; warns above the task's 3,000 characters or 60 lines; shows the service's 422 errors |
| FR04 verification | Syntax, task rubric, reference tests and model review in four separate cards, never merged into one verdict |
| FR05 diff | Unified diff parsed from the service's `diff`, and a side-by-side view of the full original and proposed code, both with syntax colors and indentation guides; an outline of the indentation before and after sits beside the outcome |
| FR06 user control | Accept and reject record a decision only; copy and download are explicit; the editor content is never changed by a run, a decision or an error |
| FR07 traceability | Run record: identifier, workflow, provider, exact model and adapter identity, the refactoring weights requested, calls and attempts against their limits, stage timings, per-attempt outcomes and raw output, stop reason in words and as its code, warnings |
| FR08 bounded execution | The run record lists each role's generation limits (new tokens, input tokens, time limit, temperature) and the run's time limit as stored with the run |
| FR10 history | Bounded history (20, or up to 50) with status, outcome, provider and decision; reopen and delete with confirmation |
| NFR06 | Every result shows that passing tests cover the trusted inputs only and do not prove equivalence for every input |

## Design decisions

| Decision | Alternatives considered | Reason |
|---|---|---|
| React 19, TypeScript and Vite, exact versions and a lock file | Server-rendered pages; a component kit | The execution plan names React and TypeScript; a kit would add weight and a generic look |
| Plain textarea with line numbers | Monaco or CodeMirror | Functions are at most 60 lines; an editor component would add several megabytes and its own accessibility questions. Tab inserts four spaces; Escape then Tab leaves the editor, and Shift+Tab is never captured, so there is no keyboard trap |
| Polling with bounded backoff | WebSocket or server-sent events | The API defines polling; runs last seconds to minutes. The first request comes after 750 ms, the delay grows by 1.5x to at most 3 s while the status is unchanged and returns to 750 ms when it changes. Only one request is in flight; polling stops on `completed` or `failed`, when the page closes and after at least 20 minutes (or twice the run's own time limit). Network, proxy and busy errors are retried without losing the shown state; 404 stops at once |
| Reference-case link derived from the code | A stored flag cleared on the first keystroke | The request carries `reference_case_id` only while the code matches the case exactly, by the server's own rule (newlines normalized, trailing whitespace ignored). An edit removes the link with a notice and undoing the edit restores it, so the interface can never send a case id the server would reject as a mismatch |
| Side-by-side alignment from the service's diff | Computing a second diff in the browser | Both views then show the same change. The alignment checks every line against both texts and falls back to two unaligned listings if they disagree; an unreadable diff is shown as raw text |
| Missing evidence drawn as absent | One color per status | Pass and accept are the only states in green with a check mark. `not_available`, `not_run` and `error` use a dashed outline, a hatched edge and their own words, and a fake provider's placeholder review is drawn the same way. Tests assert this for every status |
| Sticky warning banner in fake mode | A dismissible notice | The banner stays at the top of every scroll position, so no screenshot of a fake result can omit it; results from the fake provider are also labeled in the outcome, explanation and history |
| Decisions never edit files or the input | An "apply" button | FR06 and the API contract: the service writes nothing to host files and the download happens after inspection |
| Production build with a Content Security Policy | No policy | The page may load scripts, styles and data from its own origin only, so it works offline and cannot fetch from the internet |
| Fixed English formats; UTC for zone-less timestamps | The browser locale | The laptop's regional settings must not change the page language or date order |
| Model output shown verbatim, never parsed | Parsing the refactoring output in the browser | The service parses the model output (now the code-first refactor-v2 format) and stores the result; the interface only shows the stored raw output per attempt, so a prompt-format change needs no interface change |
| Syntax colors from a small display-only highlighter | A highlighting library (Prism, Shiki); plain monochrome code | Code is the main material of the page and color makes nested structure readable at a glance. About 250 lines cover Python's keywords, names, strings (with prefixes, escapes and triple quotes across lines), numbers and comments; the rendered text is always exactly the source line, so copying and tests see the original characters. It never interprets or changes code |
| Editor colors drawn under a transparent textarea | A code-editor component | The textarea stays the only control (keyboard, undo, screen readers and the Tab and Escape rules are unchanged); the colored copy is hidden from assistive technology and switched off in Windows forced-colors mode, where the textarea shows its own text |
| Indentation outline beside the outcome | A single depth number; no figure | Guard clauses exist to flatten nesting, so the outcome shows the outline of the original and the proposed code to the same scale, with the deepest indentation level of each. It is measured from the text by Python's block rule and is a display aid only; the service's rubric check "Reduces the nesting depth" stays the verdict |
| The four checks as one list, like a CI run | Four cards in a grid | A list keeps the four results separate, aligns their status words in one column and leaves room for the eight rubric checks without unbalanced card heights. Missing evidence keeps its dashed outline and hatched tile |
| Workflow choice and Propose refactoring in one action bar that stays in view | The button at the end of a long form | The primary action is visible on a laptop screen without scrolling; on a phone the bar stays in place so it does not cover the screen. A submission error appears above the editor, next to the code it concerns |
| JetBrains Mono for code, self-hosted (SIL OFL 1.1) | Consolas only | Cascadia Mono is not installed on the demonstration laptop and Consolas is cramped at small sizes. Two Latin files of about 21 kB each are served from the page's own origin with their license; ligatures are turned off so `>=` and `!=` show as typed |
| Not-ready reasons shown from the service's own text | A fixed message | The service knows whether the model is loading or an adapter is missing; the header labels the state (loading, adapter missing, not ready) and shows the service's detail in full |

The visual design was reworked on 2026-10-21 after the first version was judged weak. It treats the page as a developer tool whose main material is code: white panels on a cool grey page, a single cobalt accent kept for actions, focus and progress, and green, red and amber reserved for results. The code surfaces (editor, diff, listings) share one monospace face, syntax colors, indentation guides at every four columns and a quiet gutter, so the nesting that guard clauses remove is visible in every view. The outcome card leads the result with the verdict, the service's reasons and the indentation outline; the diff follows in a framed view with the layout switch and the line counts in its bar, then the four checks as one list, the explanation and findings, the decision and the run record. Interface text uses the system font (Segoe UI Variable on Windows), with semibold headings on a small scale (14 px body, 16 to 20 px headings). The fake-provider banner is a slim sticky amber bar with a warning tile; on a phone it keeps its first sentence on screen and the full text for screen readers. Light and dark themes follow the operating system. WCAG AA contrast is checked by a test for every text and background pair the stylesheet uses in both themes (4.5:1 for text, 3:1 for borders, focus rings and status bars), including each syntax color on plain, added and removed lines. Focus is always visible, every control has a label, status changes are announced through a polite live region, motion is reduced when the system asks for it, and the layout works from 380 px wide (one column, vertical stepper) to wide screens (input and history beside the result).

## Interface states and screenshots to take

Each state can be produced with the fake provider (`REFACTOR_AI_PROVIDER=fake`, the default). The screenshots in [`docs/report/screenshots/`](../screenshots/) were taken on 2026-10-21 from the simplified interface (commit `bad4095`) served on the demonstration laptop with the fine-tuned model (adapter `full-2026-10-21`, bf16) and the real reference runner, at 1440 by 900 px and 390 by 844 px; each result is one real run of the fine-tuned model, not a measured rate. The run-in-progress image was taken while the browser held back the progress requests for a few seconds without changing them, so the queued state returned by the service stayed on screen.

| ID | State | How to produce it |
|---|---|---|
| S1 | Empty page with the service status and the fake-provider banner | Open the page with the service running in fake mode |
| S2 | Demonstration case loaded and linked | Choose a case, then Load case |
| S3 | Link removed after an edit | Change one character of the loaded case |
| S4 | Run in progress with the stepper | Propose refactoring and capture during analysis or generation |
| S5 | Proposal ready: outcome, unified diff, four verification checks | Submit a demonstration case unchanged, multi-role |
| S6 | Side-by-side view with lines flagged by the analysis | Choose Side by side on S5 |
| S7 | Uncertain: reference tests not available, review not run | Single-role run of code that is not linked to a case |
| S8 | No change | Submit a function without a nested conditional, for example `def sign(x)` with an `if`/`elif` chain |
| S9 | Invalid syntax error with line and column | Submit code with a missing colon |
| S10 | Service busy | Submit while the queue is full (set `REFACTOR_AI_MAX_PENDING=1` and submit twice quickly) |
| S11 | Failed or interrupted run with Try again | Stop the service during a run, restart it and open the run from the history |
| S12 | Decision recorded and download started | Accept on S5, then Download proposal |
| S13 | History with several outcomes and delete confirmation | After S5 to S11, choose Delete on one run |
| S14 | Dark theme and phone width | Switch the operating system to dark mode; narrow the window to about 390 px |
| S15 | Header while the local model loads, and with a requested adapter missing | Start in local mode and open the page at once; or set `REFACTOR_AI_REFACTOR_USE_ADAPTER=true` with no adapter configured |
| S16 | Run failed with `adapter_unavailable` | Submit a run in the configuration of S15 with the adapter missing |

| File in `docs/report/screenshots/` | State |
|---|---|
| `s01-empty-light.png`, `s01-empty-dark.png` | S1 |
| `s02-case-loaded-light.png` | S2 |
| `s03-link-removed-light.png` | S3 |
| `s04-run-in-progress-light.png` | S4 (queued) |
| `s05-proposal-ready-light.png`, `s05-proposal-ready-dark.png` | S5, outcome with the indentation outline |
| `s05b-diff-and-verification-light.png`, `s05b-diff-and-verification-dark.png` | S5, unified diff and the start of the checks |
| `s05c-run-record-light.png` | S5, run record |
| `s06-side-by-side-light.png` | S6 |
| `s07-uncertain-single-role-light.png`, `s07b-uncertain-verification-light.png` | S7 |
| `s08-no-change-light.png` | S8 |
| `s09-invalid-syntax-light.png`, `s09-invalid-syntax-dark.png` | S9 |
| `s12-decision-recorded-light.png` | S12 (decision; the download notice is in the diff header) |
| `s13-history-delete-light.png` | S13 |
| `s14-mobile-input-*.png`, `s14-mobile-outcome-*.png`, `s14-mobile-diff-*.png`, `s14-mobile-verification-*.png` | S14 at 390 px, light and dark |

S10, S11, S15 and S16 need a full queue, a stopped service, the local model or a missing adapter, so they were not captured; their rendering is covered by the tests in `src/App.test.tsx` and `src/test/contractExamples.test.tsx`.

## Evidence

Commands run in `frontend/` on the demonstration laptop (Windows 11, Node 24.12.0, npm 11.6.2), first on 2026-10-20 and again after the redesign on 2026-10-21 (the test and build rows show the later run):

| Command | Result |
|---|---|
| `npm ci` equivalent (`npm install` from the pinned manifest) | 106 packages, 0 vulnerabilities reported by npm audit, `node_modules` about 110 MB |
| `npm run typecheck` (`tsc -b`) | Passed; a deliberately wrong type in an application file and in a test file each made it fail |
| `npm test` | 488 passed, 5 skipped (the optional end-to-end file), 0 failed, in 13 test files |
| `npm run build` | Passed: one 321 kB script (97 kB compressed), one 45 kB stylesheet (9 kB compressed) and the two font files in `frontend/dist` |

| Test file | Tests | Subject |
|---|---|---|
| `src/lib/diff.test.ts` | 22 | Unified diff parser and side-by-side alignment |
| `src/lib/highlight.test.ts` | 9 | Display-only Python highlighter and the indentation outline |
| `src/lib/polling.test.ts` | 15 | Backoff, terminal stop, `stop()`, timeout, retries, fatal errors (fake timers) |
| `src/api/client.test.ts` | 29 | Requests, error bodies, retry delay, network failure, timeout, cancellation, download names |
| `src/lib/helpers.test.ts` | 18 | Text measurement, time and duration formats, status vocabulary, reasons, `hasProposal` |
| `src/state/state.test.ts` | 14 | Run and editor reducers |
| `src/components/results.test.tsx` | 40 | Every disposition and verification status, diff views, progress steps |
| `src/components/editor.test.tsx` | 6 | Tab, Escape and Shift+Tab, line numbers |
| `src/App.test.tsx` | 39 | The whole page against a fake service, including the model-loading and missing-adapter header states |
| `src/test/contractMirror.test.ts` | 56 | TypeScript contract against `contracts.py`, task limits, API limits, the default generation limits, every coordinator stop reason and every service run-error code |
| `src/test/contractExamples.test.tsx` | 53 | Every file in `docs/architecture/examples/`, each run record rendered and each health example rendered in the header |
| `src/styles/contrast.test.ts` | 187 | WCAG contrast of the color pairs in both themes, including syntax colors on code, added and removed lines |
| `src/test/e2e.test.ts` | 5 | Optional, against a running service |

The end-to-end file was run once against the real service on a private port, with the fake provider, the real coordinator and the real reference runner, and a database in a temporary folder: all 5 tests passed. They covered a demonstration case completed with verification, a diff that parses and aligns, the downloaded file's content and name, a recorded decision, a single-role run without review, the `invalid_syntax`, `reference_case_mismatch`, `unknown_reference_case` and `run_not_found` errors, and deletion. All six demonstration cases completed as `proposal_ready` with every reference test passing; with the fake provider this shows the plumbing only.

The built interface was also checked in a headless browser served by that service, at 1440 px and 390 px, in light and dark themes. This found and fixed a side-by-side table that grew to 4,400 px (a percentage column width), screen-reader text that widened the page from inside a scroll box, notices whose bold words broke onto their own lines, a fake placeholder review that still showed a check mark and an unbalanced three-plus-one card grid.

The redesign of 2026-10-21 was checked the same way against the real service in fake mode, at 1280, 1440 and 390 px in both themes, for every state in the screenshot list. Problems found and fixed on the way: the primary button and the workflow choice fell below the fold on a laptop screen (now in the action bar), a syntax error appeared below the fold (now above the editor), the outcome title wrapped beside the outline on narrower screens (the outline moves under the text through a container query), the five-step stepper's labels collided at 390 px (vertical stepper on phones), and a notice built as a flex column broke its bold case name onto separate lines. The existing behavior tests passed without changes; the contrast test gained pairs for the new color tokens, and a new test file covers the highlighter and the outline.

## Known limitations

- The screenshots show single runs of the fine-tuned model on the simplified interface; S10, S11, S15 and S16 were not captured.
- The highlighter and the indentation outline are display aids written for this one task; they do not handle every corner of Python's grammar (for example f-string nesting or line continuations with a backslash), and a wrong color or outline never changes the code, the request or a result.
- The browser checks were manual; there is no automated browser test, by design (no Playwright dependency).
- Without ESLint, React hook dependency rules are not checked mechanically; effects were reviewed by hand and the unmount behavior is tested.
- Elapsed time while a run is active uses the browser clock against the service's `created_at`; both run on the same machine.
- The interface polls; it does not receive pushed updates. A run that outlasts the maximum wait keeps running on the server and can be checked again from the page or the history.
