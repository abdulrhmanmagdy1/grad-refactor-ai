import type { RefObject } from "react";
import type { HumanDecision, RunRecord, RunStatus } from "../api/contracts";
import { hasProposal, isTerminalStatus } from "../api/contracts";
import { useNow } from "../hooks/useNow";
import { formatDateTime, formatDuration, formatElapsed, parseServerTime, secondsBetween, shortId } from "../lib/format";
import { PROVIDER_LABELS, RUN_STATUS_META, WORKFLOW_META, runErrorHint, stepForStage } from "../lib/labels";
import type { RunEntry } from "../state/runs";
import { AnalysisSection } from "./AnalysisSection";
import { type DecisionState, DecisionPanel } from "./DecisionPanel";
import { CodeListing, DiffViewer } from "./DiffViewer";
import { DispositionBanner, ReasonList } from "./DispositionBanner";
import type { SubmissionFailure } from "./InputPanel";
import { ProgressStepper } from "./ProgressStepper";
import { ProposalActions } from "./ProposalActions";
import { RunDetails } from "./RunDetails";
import { SubmissionErrorView } from "./SubmissionError";
import { VerificationPanel } from "./VerificationPanel";

export interface RetryState {
  runId: string | null;
  pending: boolean;
  failure: SubmissionFailure | null;
}

export interface RunPanelProps {
  entry: RunEntry | null;
  headingRef: RefObject<HTMLHeadingElement | null>;
  /** True when the page-wide fake-provider banner is already visible. */
  fakeBannerShown: boolean;
  /** True when the editor still holds exactly this run's input. */
  editorHoldsInput: boolean;
  submitBlocked: boolean;
  decision: DecisionState;
  retry: RetryState;
  onDecide: (runId: string, decision: HumanDecision) => void;
  onResume: (runId: string) => void;
  onReload: (runId: string) => void;
  onTryAgain: (record: RunRecord) => void;
  onLoadInput: (record: RunRecord) => void;
}

export function RunPanel(props: RunPanelProps) {
  const { entry, headingRef } = props;
  const created = entry?.record?.created_at ?? null;
  return (
    <section className="panel run-panel" aria-labelledby="run-heading">
      <div className="panel__head">
        <h2 id="run-heading" ref={headingRef} tabIndex={-1}>
          Run
        </h2>
        <p className="panel__sub">
          {entry ? (
            <>
              Run <span className="mono">{shortId(entry.runId)}</span>
              {created ? `, created ${formatDateTime(created)}` : null}
            </>
          ) : (
            "Progress and results appear here"
          )}
        </p>
      </div>
      {entry ? <RunBody {...props} entry={entry} /> : <EmptyRun />}
    </section>
  );
}

function EmptyRun() {
  return (
    <div className="empty">
      <p className="empty__title">No run selected</p>
      <p>
        Paste a Python function into the editor or load a demonstration case, then choose Propose refactoring. You can
        also open an earlier run from the history.
      </p>
    </div>
  );
}

function RunBody(props: RunPanelProps & { entry: RunEntry }) {
  const { entry, onReload } = props;
  const record = entry.record;

  if (!record && entry.loading) {
    return (
      <p className="loading" role="status">
        Loading the run…
      </p>
    );
  }
  if (!record && entry.error && !entry.request) {
    return (
      <div className="notice" data-tone="fail">
        <p>Could not load this run: {entry.error.message}</p>
        <div className="notice__actions">
          <button type="button" className="button button--small" onClick={() => onReload(entry.runId)}>
            Try again
          </button>
        </div>
      </div>
    );
  }

  const status: RunStatus | null = record?.status ?? entry.knownStatus;
  const terminal = status !== null && isTerminalStatus(status);
  const mode = record?.workflow_mode ?? entry.request?.workflow_mode ?? "multi_role";

  return (
    <>
      {record ? <RunSummaryLine record={record} onLoadInput={props.onLoadInput} /> : null}
      {record && record.provider_mode === "fake" && !props.fakeBannerShown ? (
        <p className="notice" data-tone="warn">
          This run used the fake test provider. Its output is not from a language model.
        </p>
      ) : null}
      <ProgressBlock entry={entry} status={status} mode={mode} terminal={terminal} />
      <PollNotices entry={entry} onResume={props.onResume} onReload={onReload} />
      {record && record.status === "failed" ? <FailureView {...props} record={record} /> : null}
      {record && record.status === "completed" ? <ResultView {...props} record={record} /> : null}
      {!terminal ? (
        <p className="waiting-note">
          Results appear here when the run finishes. You can keep editing your code in the meantime.
        </p>
      ) : null}
      {record && terminal ? <RunDetails record={record} /> : null}
    </>
  );
}

function RunSummaryLine({ record, onLoadInput }: { record: RunRecord; onLoadInput: (record: RunRecord) => void }) {
  return (
    <div className="run-summary">
      <ul className="run-summary__facts">
        <li>{WORKFLOW_META[record.workflow_mode].label} workflow</li>
        <li>{PROVIDER_LABELS[record.provider_mode]}</li>
        <li>
          {record.reference_case_id ? (
            <>
              Reference case <span className="mono">{record.reference_case_id}</span>
            </>
          ) : (
            "No reference case"
          )}
        </li>
      </ul>
      <button type="button" className="button button--small button--quiet" onClick={() => onLoadInput(record)}>
        Edit this input
      </button>
    </div>
  );
}

function ProgressBlock({
  entry,
  status,
  mode,
  terminal,
}: {
  entry: RunEntry;
  status: RunStatus | null;
  mode: RunRecord["workflow_mode"];
  terminal: boolean;
}) {
  const ticking = entry.poll === "polling" && !terminal;
  const now = useNow(ticking);
  const record = entry.record;
  const start = parseServerTime(record?.created_at) ?? entry.trackedSince;
  const total = record ? secondsBetween(record.created_at, record.finished_at) : null;
  const meta = status ? RUN_STATUS_META[status] : null;
  return (
    <div className="progress">
      <ProgressStepper mode={mode} status={status} trail={entry.statusTrail} errorStage={record?.error?.stage ?? null} />
      <p className="progress__status">
        <span>
          {meta ? (
            <>
              <strong>{meta.label}.</strong> {meta.activity}
            </>
          ) : (
            "Waiting for the first status update."
          )}
        </span>
        {ticking ? (
          <span className="progress__time">Elapsed {formatElapsed(Math.max(0, now - start))}</span>
        ) : terminal && total !== null ? (
          <span className="progress__time">Total {formatDuration(total)}</span>
        ) : null}
      </p>
    </div>
  );
}

function PollNotices({
  entry,
  onResume,
  onReload,
}: {
  entry: RunEntry;
  onResume: (runId: string) => void;
  onReload: (runId: string) => void;
}) {
  if (entry.retry && entry.poll === "polling") {
    return (
      <p className="notice" data-tone="warn" role="status">
        Connection problem: {entry.retry.error.message} Checking again automatically (attempt {entry.retry.attempt}).
        The run and your input are kept.
      </p>
    );
  }
  if (entry.poll === "timed_out") {
    return (
      <div className="notice" data-tone="warn" role="status">
        <p>
          Stopped checking after {formatElapsed(entry.timedOutAfterMs ?? 0)}. The run may still be in progress on the
          server.
          {entry.error ? ` The last check failed: ${entry.error.message}` : ""}
        </p>
        <div className="notice__actions">
          <button type="button" className="button button--small" onClick={() => onResume(entry.runId)}>
            Check again
          </button>
        </div>
      </div>
    );
  }
  if (entry.poll === "failed" && entry.error) {
    const missing = entry.error.code === "run_not_found";
    return (
      <div className="notice" data-tone="fail" role="status">
        <p>
          {missing
            ? "This run no longer exists on the server. It may have been deleted."
            : `Progress could not be loaded: ${entry.error.message}`}
        </p>
        {missing ? null : (
          <div className="notice__actions">
            <button type="button" className="button button--small" onClick={() => onResume(entry.runId)}>
              Check again
            </button>
          </div>
        )}
      </div>
    );
  }
  if (entry.record && entry.error && !entry.loading) {
    return (
      <div className="notice" data-tone="warn" role="status">
        <p>Could not refresh this run: {entry.error.message} The last known state is shown.</p>
        <div className="notice__actions">
          <button type="button" className="button button--small" onClick={() => onReload(entry.runId)}>
            Try again
          </button>
        </div>
      </div>
    );
  }
  return null;
}

function WarningsNotice({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) return null;
  return (
    <div className="notice" data-tone="warn">
      <p className="notice__title">Warnings recorded for this run</p>
      <ul className="notice__list">
        {warnings.map((warning, index) => (
          <li key={index}>{warning}</li>
        ))}
      </ul>
    </div>
  );
}

function FailureView(props: RunPanelProps & { entry: RunEntry; record: RunRecord }) {
  const { record, retry, submitBlocked, onTryAgain, onLoadInput, editorHoldsInput } = props;
  const error = record.error;
  const hint = error ? runErrorHint(error.code) : null;
  const step = stepForStage(error?.stage);
  const retrying = retry.runId === record.run_id;
  return (
    <>
      <section className="failure" aria-labelledby="failure-heading">
        <h3 id="failure-heading" className="failure__title">
          The run failed
        </h3>
        {error ? (
          <p className="failure__message">
            <code className="code-tag">{error.code}</code> {error.message}
          </p>
        ) : (
          <p className="failure__message">The service did not record an error message.</p>
        )}
        {hint ? <p>{hint}</p> : null}
        {error?.stage ? (
          <p className="muted">
            Stopped during: {step ? RUN_STATUS_META[step].label.toLowerCase() : error.stage}
          </p>
        ) : null}
        {record.verification ? <ReasonList reasons={record.verification.disposition_reasons} /> : null}
        <p>
          {editorHoldsInput
            ? "Your input is unchanged in the editor."
            : "The original input is kept with this run and shown below."}
        </p>
        <div className="failure__actions">
          <button
            type="button"
            className="button button--primary"
            onClick={() => onTryAgain(record)}
            disabled={submitBlocked}
          >
            {retrying && retry.pending ? "Submitting…" : "Try again"}
          </button>
          <button type="button" className="button" onClick={() => onLoadInput(record)}>
            Edit this input
          </button>
        </div>
        {retrying && retry.failure ? (
          <SubmissionErrorView
            error={retry.failure.error}
            location={null}
            inputNote="The original input is unchanged."
          />
        ) : null}
      </section>
      <WarningsNotice warnings={record.warnings} />
      <div className="result-section">
        <CodeListing title="Original input" code={record.original_code} findings={record.findings} />
      </div>
      {record.findings.length > 0 || record.analysis ? <AnalysisSection record={record} /> : null}
    </>
  );
}

function ResultView(props: RunPanelProps & { entry: RunEntry; record: RunRecord }) {
  const { record, decision, onDecide } = props;
  const fake = record.provider_mode === "fake";
  const proposal = hasProposal(record);
  const disposition = record.verification?.disposition ?? null;
  return (
    <>
      <DispositionBanner verification={record.verification} fake={fake} />
      <WarningsNotice warnings={record.warnings} />
      {proposal && record.proposed_code !== null ? (
        <DiffViewer
          original={record.original_code}
          proposed={record.proposed_code}
          diff={record.diff}
          findings={record.findings}
          actions={<ProposalActions runId={record.run_id} proposedCode={record.proposed_code} />}
        />
      ) : (
        <div className="result-section">
          <p className="muted">
            {disposition === "no_change"
              ? "No proposal: the original code stays as it is."
              : "No proposal was produced, so there is nothing to compare or download."}
          </p>
          <CodeListing title="Original input" code={record.original_code} findings={record.findings} />
        </div>
      )}
      {record.verification ? (
        <VerificationPanel
          verification={record.verification}
          review={record.review}
          mode={record.workflow_mode}
          fake={fake}
          hasProposal={proposal}
        />
      ) : null}
      <AnalysisSection record={record} />
      {proposal ? (
        <DecisionPanel
          decision={record.human_decision}
          disposition={disposition}
          state={decision}
          onDecide={(choice) => onDecide(record.run_id, choice)}
        />
      ) : null}
    </>
  );
}
