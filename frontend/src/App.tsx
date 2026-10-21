import { useCallback, useReducer, useRef, useState } from "react";
import {
  type ApiError,
  createRun,
  deleteRun,
  getHealth,
  getRun,
  listReferenceCases,
  listRuns,
  recordDecision,
  toApiError,
} from "./api/client";
import {
  type HumanDecision,
  RUN_LIST_DEFAULT_LIMIT,
  RUN_LIST_MAX_LIMIT,
  type RunCreateRequest,
  type RunRecord,
  TASK_TYPE,
} from "./api/contracts";
import { AppHeader, FakeProviderBanner } from "./components/AppHeader";
import type { DecisionState } from "./components/DecisionPanel";
import { HistoryPanel } from "./components/HistoryPanel";
import { InputPanel, type SubmissionFailure } from "./components/InputPanel";
import { ProjectView } from "./components/ProjectView";
import { type RetryState, RunPanel } from "./components/RunPanel";
import { RunPoller } from "./components/RunPoller";
import { useResource } from "./hooks/useResource";
import { shortId } from "./lib/format";
import { DISPOSITION_META, RUN_STATUS_META } from "./lib/labels";
import { type PollEvent, maxWaitForRun } from "./lib/polling";
import { matchesCaseCode, normalizeNewlines } from "./lib/text";
import { editorReducer, initialEditorState, linkedCase } from "./state/editor";
import { type RunEntry, initialRunsState, isAnyRunActive, runsReducer, selectedEntry } from "./state/runs";

const HEALTH_REFRESH_MS = 30_000;
const IDLE_DECISION: DecisionState = { pending: null, error: null };
const NO_RETRY: RetryState = { runId: null, pending: false, failure: null };

function announce(entry: RunEntry | null): string {
  if (!entry || !entry.knownStatus) return "";
  const status = entry.knownStatus;
  if (status === "completed") {
    const disposition = entry.record?.verification?.disposition;
    return disposition ? `Run completed: ${DISPOSITION_META[disposition].label}.` : "Run completed.";
  }
  if (status === "failed") {
    const code = entry.record?.error?.code;
    return code ? `Run failed: ${code}.` : "Run failed.";
  }
  return `Run status: ${RUN_STATUS_META[status].label}.`;
}

export function App() {
  const health = useResource(getHealth, { refreshMs: HEALTH_REFRESH_MS });
  const cases = useResource(listReferenceCases);
  const [historyLimit, setHistoryLimit] = useState(RUN_LIST_DEFAULT_LIMIT);
  const history = useResource((signal) => listRuns(historyLimit, signal), { key: historyLimit });

  const [editor, editorDispatch] = useReducer(editorReducer, initialEditorState);
  const [runs, runsDispatch] = useReducer(runsReducer, initialRunsState);
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<SubmissionFailure | null>(null);
  const [retry, setRetry] = useState<RetryState>(NO_RETRY);
  const [decisions, setDecisions] = useState<Record<string, DecisionState>>({});
  const [view, setView] = useState<"function" | "project">("function");

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const runHeadingRef = useRef<HTMLHeadingElement>(null);
  const historyHeadingRef = useRef<HTMLHeadingElement>(null);

  const linked = linkedCase(editor);
  const runActive = isAnyRunActive(runs);
  const selected = selectedEntry(runs);
  const fakeMode =
    health.data !== null && (health.data.mode === "fake" || health.data.provider.provider_mode === "fake");
  const refreshHistory = history.refresh;
  const refreshHealth = health.refresh;

  /** Sends a run request; returns the error instead of throwing so callers keep their input. */
  const startRun = async (request: RunCreateRequest): Promise<ApiError | null> => {
    try {
      const accepted = await createRun(request);
      runsDispatch({ type: "submitted", accepted, request, now: Date.now() });
      runHeadingRef.current?.focus();
      refreshHistory();
      refreshHealth();
      return null;
    } catch (error) {
      return toApiError(error);
    }
  };

  const submitFromEditor = async () => {
    if (submitting || runActive) return;
    const code = editor.code;
    const request: RunCreateRequest = {
      code,
      task_type: TASK_TYPE,
      workflow_mode: editor.workflowMode,
      reference_case_id: linked ? linked.case_id : null,
    };
    setSubmitting(true);
    setFailure(null);
    const error = await startRun(request);
    setSubmitting(false);
    if (error) setFailure({ error, code });
  };

  const tryAgain = async (record: RunRecord) => {
    if (submitting || runActive) return;
    const request: RunCreateRequest = {
      code: record.original_code,
      task_type: TASK_TYPE,
      workflow_mode: record.workflow_mode,
      reference_case_id: record.reference_case_id,
    };
    setSubmitting(true);
    setRetry({ runId: record.run_id, pending: true, failure: null });
    const error = await startRun(request);
    setSubmitting(false);
    setRetry(error ? { runId: record.run_id, pending: false, failure: { error, code: record.original_code } } : NO_RETRY);
  };

  const onPollEvent = useCallback(
    (runId: string, event: PollEvent) => {
      runsDispatch({ type: "poll", runId, event });
      if (event.type === "terminal") {
        refreshHistory();
        refreshHealth();
      }
    },
    [refreshHistory, refreshHealth],
  );

  const openRun = async (runId: string) => {
    const existing = runs.entries[runId];
    runsDispatch({ type: "open", runId, now: Date.now() });
    runHeadingRef.current?.focus();
    if (existing?.poll === "polling") return;
    try {
      runsDispatch({ type: "loaded", record: await getRun(runId) });
    } catch (error) {
      runsDispatch({ type: "load_failed", runId, error: toApiError(error) });
    }
  };

  const removeRun = async (runId: string) => {
    try {
      await deleteRun(runId);
    } catch (error) {
      const apiError = toApiError(error);
      // Already gone on the server: treat it as deleted.
      if (apiError.code !== "run_not_found") throw apiError;
    }
    runsDispatch({ type: "removed", runId });
    setDecisions((current) => {
      const next = { ...current };
      delete next[runId];
      return next;
    });
    historyHeadingRef.current?.focus();
    refreshHistory();
  };

  const decide = async (runId: string, decision: HumanDecision) => {
    setDecisions((current) => ({ ...current, [runId]: { pending: decision, error: null } }));
    let updated: RunRecord | null;
    try {
      updated = await recordDecision(runId, decision);
    } catch (error) {
      setDecisions((current) => ({ ...current, [runId]: { pending: null, error: toApiError(error) } }));
      return;
    }
    setDecisions((current) => ({ ...current, [runId]: IDLE_DECISION }));
    try {
      runsDispatch({ type: "loaded", record: updated ?? (await getRun(runId)) });
    } catch {
      // The decision is stored; the history refresh below shows it even if this reload failed.
    }
    refreshHistory();
  };

  const loadInput = (record: RunRecord) => {
    const matching =
      record.reference_case_id !== null
        ? (cases.data?.find(
            (item) => item.case_id === record.reference_case_id && matchesCaseCode(record.original_code, item.code),
          ) ?? null)
        : null;
    editorDispatch({
      type: "load_input",
      code: record.original_code,
      mode: record.workflow_mode,
      linkedCase: matching,
      label: `run ${shortId(record.run_id)}`,
    });
    setFailure(null);
    textareaRef.current?.focus();
  };

  const selectedRecord = selected?.record ?? null;
  const editorHoldsInput =
    selectedRecord !== null && normalizeNewlines(editor.code) === normalizeNewlines(selectedRecord.original_code);

  return (
    <div className="app">
      <a className="skip-link" href="#main-content">
        Skip to the editor
      </a>
      <AppHeader health={health.data} error={health.error} loading={health.loading} onRetry={health.refresh} />
      {fakeMode ? <FakeProviderBanner /> : null}
      <nav className="mode-tabs" aria-label="What to review">
        <button
          type="button"
          className="mode-tabs__tab"
          aria-pressed={view === "function"}
          onClick={() => setView("function")}
        >
          One function
        </button>
        <button
          type="button"
          className="mode-tabs__tab"
          aria-pressed={view === "project"}
          onClick={() => setView("project")}
        >
          Whole project
        </button>
      </nav>
      {view === "project" ? (
        <main id="main-content" className="layout layout--project" tabIndex={-1}>
          <ProjectView />
        </main>
      ) : (
      <main id="main-content" className="layout" tabIndex={-1}>
        <div className="layout__input">
          <InputPanel
            editor={editor}
            linked={linked}
            dispatch={editorDispatch}
            cases={{ data: cases.data, error: cases.error, loading: cases.loading }}
            onReloadCases={cases.refresh}
            runActive={runActive}
            submitting={submitting}
            failure={failure}
            onSubmit={() => void submitFromEditor()}
            onDismissFailure={() => setFailure(null)}
            textareaRef={textareaRef}
          />
        </div>
        <div className="layout__run">
          <RunPanel
            entry={selected}
            headingRef={runHeadingRef}
            fakeBannerShown={fakeMode}
            editorHoldsInput={editorHoldsInput}
            submitBlocked={submitting || runActive}
            decision={(selected && decisions[selected.runId]) || IDLE_DECISION}
            retry={retry}
            onDecide={(runId, decision) => void decide(runId, decision)}
            onResume={(runId) => runsDispatch({ type: "resume", runId })}
            onReload={(runId) => void openRun(runId)}
            onTryAgain={(record) => void tryAgain(record)}
            onLoadInput={loadInput}
          />
        </div>
        <div className="layout__history">
          <HistoryPanel
            runs={history.data?.runs ?? null}
            limit={historyLimit}
            loading={history.loading}
            error={history.error}
            selectedId={runs.selectedId}
            headingRef={historyHeadingRef}
            onRefresh={history.refresh}
            onShowMore={() => setHistoryLimit(RUN_LIST_MAX_LIMIT)}
            onOpen={(runId) => void openRun(runId)}
            onDelete={removeRun}
          />
        </div>
      </main>
      )}
      <footer className="app-footer">
        <p>
          Runs on this machine. Your code is never executed by the web service.
        </p>
      </footer>
      <p className="visually-hidden" role="status" aria-live="polite">
        {announce(selected)}
      </p>
      {Object.values(runs.entries)
        .filter((entry) => entry.poll === "polling")
        .map((entry) => (
          <RunPoller
            key={entry.runId}
            runId={entry.runId}
            generation={entry.pollGeneration}
            initialStatus={entry.knownStatus}
            maxWaitMs={maxWaitForRun(entry.record?.settings.run_timeout_s)}
            onEvent={onPollEvent}
          />
        ))}
    </div>
  );
}
