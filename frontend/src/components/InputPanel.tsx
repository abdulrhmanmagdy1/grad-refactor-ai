import { type FormEvent, type RefObject, useId, useState } from "react";
import type { ApiError } from "../api/client";
import {
  MAX_CODE_CHARS,
  type ReferenceCaseSummary,
  TASK_MAX_CHARS,
  TASK_MAX_LINES,
  TASK_TYPE,
  WORKFLOW_MODES,
} from "../api/contracts";
import { formatCount, plural } from "../lib/format";
import { TASK_LABEL, WORKFLOW_META } from "../lib/labels";
import { countCodePoints, countLines, isBlank, lineOffsets } from "../lib/text";
import { type EditorAction, type EditorState, caseTitle } from "../state/editor";
import { CodeEditor } from "./CodeEditor";
import { type SyntaxLocation, SubmissionErrorView, syntaxLocation } from "./SubmissionError";

export interface SubmissionFailure {
  error: ApiError;
  /** The code that was sent, to tell whether a reported line still applies. */
  code: string;
}

export interface CasesState {
  data: ReferenceCaseSummary[] | null;
  error: ApiError | null;
  loading: boolean;
}

interface InputPanelProps {
  editor: EditorState;
  linked: ReferenceCaseSummary | null;
  dispatch: (action: EditorAction) => void;
  cases: CasesState;
  onReloadCases: () => void;
  runActive: boolean;
  submitting: boolean;
  failure: SubmissionFailure | null;
  onSubmit: () => void;
  onDismissFailure: () => void;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
}

export function InputPanel({
  editor,
  linked,
  dispatch,
  cases,
  onReloadCases,
  runActive,
  submitting,
  failure,
  onSubmit,
  onDismissFailure,
  textareaRef,
}: InputPanelProps) {
  const ids = useId();
  const editorId = `${ids}-code`;
  const helpId = `${ids}-help`;
  const counterId = `${ids}-counter`;
  const limitId = `${ids}-limit`;
  const [selectedCaseId, setSelectedCaseId] = useState("");

  const characters = countCodePoints(editor.code);
  const lines = countLines(editor.code);
  const blank = isBlank(editor.code);
  const overApiLimit = characters > MAX_CODE_CHARS;
  const overTaskLimit = characters > TASK_MAX_CHARS || lines > TASK_MAX_LINES;
  const canSubmit = !blank && !overApiLimit && !runActive && !submitting;

  const location = syntaxLocation(failure?.error ?? null);
  const locationApplies = location !== null && failure !== null && failure.code === editor.code;
  const loadedCase = editor.loadedCase;
  const selectedCase = cases.data?.find((item) => item.case_id === selectedCaseId) ?? null;

  const goToLine = (target: SyntaxLocation) => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    const offsets = lineOffsets(textarea.value, target.line);
    if (!offsets) return;
    textarea.focus();
    textarea.setSelectionRange(offsets.start, offsets.end);
    const lineHeight = Number.parseFloat(getComputedStyle(textarea).lineHeight) || 21;
    textarea.scrollTop = Math.max(0, (target.line - 3) * lineHeight);
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (canSubmit) onSubmit();
  };

  let submitHint: string | null = null;
  if (submitting) submitHint = "Sending…";
  else if (runActive) submitHint = "Wait for the current run to finish.";
  else if (overApiLimit) submitHint = "Shorten the code to submit it.";

  return (
    <section className="panel input-panel" aria-labelledby={`${ids}-heading`}>
      <div className="panel__head">
        <h2 id={`${ids}-heading`}>Input</h2>
      </div>

      <form className="input-form" onSubmit={submit} noValidate>
        <div className="field">
          <label className="field__label" htmlFor={`${ids}-case`}>
            Demonstration case
          </label>
          <div className="case-picker">
            <select
              id={`${ids}-case`}
              className="select"
              value={selectedCaseId}
              onChange={(event) => setSelectedCaseId(event.target.value)}
              disabled={cases.loading || !cases.data || cases.data.length === 0}
              aria-describedby={`${ids}-case-help`}
            >
              <option value="">
                {cases.loading
                  ? "Loading cases…"
                  : cases.data && cases.data.length === 0
                    ? "No cases on the server"
                    : "Choose a case"}
              </option>
              {(cases.data ?? []).map((item) => (
                <option key={item.case_id} value={item.case_id}>
                  {caseTitle(item)} ({plural(item.test_count, "reference test")})
                </option>
              ))}
            </select>
            <button
              type="button"
              className="button"
              disabled={selectedCase === null}
              onClick={() => {
                if (selectedCase) dispatch({ type: "load_case", referenceCase: selectedCase });
              }}
            >
              Load case
            </button>
          </div>
          <p className="field__hint" id={`${ids}-case-help`}>
            Demo cases come with tests.
          </p>
          {cases.error ? (
            <p className="field-message" data-tone="fail">
              Could not load the demonstration cases: {cases.error.message}{" "}
              <button type="button" className="link-button" onClick={onReloadCases}>
                Try again
              </button>
            </p>
          ) : null}
        </div>

        <div className="notices" aria-live="polite">
          {loadedCase && linked ? (
            <p className="notice" data-tone="info">
              Demo case <strong>{caseTitle(loadedCase)}</strong>: {plural(loadedCase.test_count, "test")} will run.
            </p>
          ) : null}
          {loadedCase && !linked ? (
            <div className="notice" data-tone="warn">
              <p>
                You changed the demo code, so the tests of <strong>{caseTitle(loadedCase)}</strong> will not run.
              </p>
              <div className="notice__actions">
                <button type="button" className="button button--small" onClick={() => dispatch({ type: "reset_case_code" })}>
                  Restore the case code
                </button>
                <button
                  type="button"
                  className="button button--small button--quiet"
                  onClick={() => dispatch({ type: "unlink_case" })}
                >
                  Dismiss
                </button>
              </div>
            </div>
          ) : null}
          {editor.restore ? (
            <div className="notice" data-tone="neutral">
              <p>{editor.restore.message}</p>
              <div className="notice__actions">
                <button type="button" className="button button--small" onClick={() => dispatch({ type: "restore" })}>
                  Restore previous code
                </button>
                <button
                  type="button"
                  className="button button--small button--quiet"
                  onClick={() => dispatch({ type: "dismiss_restore" })}
                >
                  Dismiss
                </button>
              </div>
            </div>
          ) : null}
        </div>

        {failure ? (
          <SubmissionErrorView
            error={failure.error}
            location={location}
            onGoToLine={locationApplies ? goToLine : undefined}
            onUnlinkCase={() => dispatch({ type: "unlink_case" })}
            onRestoreCaseCode={loadedCase ? () => dispatch({ type: "reset_case_code" }) : undefined}
            onReloadCases={onReloadCases}
            onRetry={onSubmit}
            retryDisabled={!canSubmit}
            onDismiss={onDismissFailure}
          />
        ) : null}

        <div className="field">
          <div className="editor-label-row">
            <label className="field__label" htmlFor={editorId}>
              Python function
            </label>
            <p className="counter" id={counterId} data-state={overApiLimit ? "error" : overTaskLimit ? "warn" : "ok"}>
              <span>
                {formatCount(characters)} of {formatCount(MAX_CODE_CHARS)} characters
              </span>
              <span>{plural(lines, "line")}</span>
            </p>
          </div>
          <CodeEditor
            id={editorId}
            value={editor.code}
            onChange={(code) => dispatch({ type: "edit", code })}
            errorLine={locationApplies ? location.line : null}
            describedBy={`${helpId} ${counterId} ${limitId}`}
            invalid={overApiLimit || locationApplies}
            textareaRef={textareaRef}
          />
          <p className="field__hint" id={helpId}>
            Tab adds 4 spaces. Press Esc, then Tab, to leave.
          </p>
          <div id={limitId} aria-live="polite">
            {overApiLimit ? (
              <p className="field-message" data-tone="fail">
                The code is longer than the service accepts ({formatCount(MAX_CODE_CHARS)} characters). Shorten it to
                submit.
              </p>
            ) : overTaskLimit ? (
              <p className="field-message" data-tone="warn">
                The supported task takes at most {formatCount(TASK_MAX_CHARS)} characters and {TASK_MAX_LINES} lines.
                Longer input is accepted, but the run will end with no change (too_long).
              </p>
            ) : null}
          </div>
        </div>

        <div className="field">
          <label className="field__label" htmlFor={`${ids}-task`}>
            Refactoring task
          </label>
          <select id={`${ids}-task`} className="select" value={TASK_TYPE} onChange={() => undefined}>
            <option value={TASK_TYPE}>{TASK_LABEL}</option>
          </select>
        </div>

        <div className="submit-row">
          <div className="submit-row__controls">
            <fieldset className="choice-group">
              <legend className="visually-hidden">Workflow</legend>
              <div className="segmented segmented--block">
                {WORKFLOW_MODES.map((mode) => (
                  <label key={mode} className="segmented__option">
                    <input
                      type="radio"
                      name={`${ids}-workflow`}
                      value={mode}
                      checked={editor.workflowMode === mode}
                      onChange={() => dispatch({ type: "set_mode", mode })}
                    />
                    <span>
                      {WORKFLOW_META[mode].label}
                      {mode === "multi_role" ? <span className="choice__default"> (default)</span> : null}
                      <span className="visually-hidden">: {WORKFLOW_META[mode].description}</span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
            <button type="submit" className="button button--primary button--large" disabled={!canSubmit}>
              {submitting ? (
                "Submitting…"
              ) : (
                <>
                  <svg className="icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
                    <path d="M4.5 2.8v10.4L13 8Z" fill="currentColor" />
                  </svg>
                  Improve code
                </>
              )}
            </button>
          </div>
          <p className="submit-row__hint">
            {submitHint ?? (
              <span aria-hidden="true">
                {WORKFLOW_META[editor.workflowMode].label}: {WORKFLOW_META[editor.workflowMode].description}
              </span>
            )}
          </p>
        </div>
      </form>
    </section>
  );
}
