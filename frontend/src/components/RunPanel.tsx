import type { ReactNode, RefObject } from "react";
import type { HumanDecision, RunRecord, RunStatus } from "../api/contracts";
import { hasProposal, isTerminalStatus } from "../api/contracts";
import { useNow } from "../hooks/useNow";
import { formatDateTime, formatDuration, formatElapsed, parseServerTime, secondsBetween, shortId } from "../lib/format";
import { PROVIDER_LABELS, RUN_STATUS_META, WORKFLOW_META, runErrorHint, stepForStage } from "../lib/labels";
import type { RunEntry } from "../state/runs";
import { AnalysisSection } from "./AnalysisSection";
import { CheckRow } from "./CheckRow";
import { ShapeComparison, ShapeIllustration } from "./CodeShape";
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
          Result
        </h2>
        {entry && created ? (
          <p className="panel__sub">
            <span className="mono">{shortId(entry.runId)}</span>, {formatDateTime(created)}
          </p>
        ) : null}
      </div>
      {entry ? <RunBody {...props} entry={entry} /> : <EmptyRun />}
    </section>
  );
}

const PIPELINE: Array<{ title: string; text: string }> = [
  { title: "Find", text: "Spots nested if statements." },
  { title: "Rewrite", text: "Turns them into early returns." },
  { title: "Check", text: "Runs four checks on the new code." },
];

function EmptyRun() {
  return (
    <div className="empty">
      <ShapeIllustration />
      <p className="empty__title">No result yet</p>
      <p className="empty__text">Paste a function or pick a demo case, then press Improve code.</p>
      <ol className="pipeline" aria-label="What the tool does">
        {PIPELINE.map((step, index) => (
          <li key={step.title} className="pipeline__step">
            <span className="pipeline__index" aria-hidden="true">
              {index + 1}
            </span>
            <span className="pipeline__title">{step.title}</span>
            <span className="pipeline__text">{step.text}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

/** Placeholder shapes for the result while a run is in progress. */
function ResultSkeleton() {
  return (
    <div className="skeleton" aria-hidden="true">
      <div className="skeleton__block skeleton__block--outcome" />
      <div className="skeleton__block skeleton__block--diff">
        {[0, 1, 2, 3, 4, 5, 6].map((index) => (
          <span key={index} className="skeleton__line" />
        ))}
      </div>
      <div className="skeleton__row">
        <div className="skeleton__block" />
        <div className="skeleton__block" />
      </div>
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
          Demo mode: this result is not from the AI model.
        </p>
      ) : null}
      {status === "completed" ? null : (
        <ProgressBlock entry={entry} status={status} mode={mode} terminal={terminal} />
      )}
      <PollNotices entry={entry} onResume={props.onResume} onReload={onReload} />
      {record && record.status === "failed" ? <FailureView {...props} record={record} /> : null}
      {record && record.status === "completed" ? <ResultView {...props} record={record} /> : null}
      {!terminal ? (
        <>
          <p className="waiting-note">Working on it. You can keep editing.</p>
          <ResultSkeleton />
        </>
      ) : null}
    </>
  );
}

function RunSummaryLine({ record, onLoadInput }: { record: RunRecord; onLoadInput: (record: RunRecord) => void }) {
  return (
    <div className="run-summary">
      <ul className="run-summary__facts">
        <li>{WORKFLOW_META[record.workflow_mode].label}</li>
        <li>{PROVIDER_LABELS[record.provider_mode]}</li>
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

/** Everything beyond the verdict, the change and the decision, closed by default. */
function DetailsDrawer({ children }: { children: ReactNode }) {
  return (
    <details className="details-drawer">
      <summary className="details-drawer__summary">Details</summary>
      <div className="details-drawer__body">{children}</div>
    </details>
  );
}

function WarningsNotice({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) return null;
  return (
    <div className="notice" data-tone="warn">
      <p className="notice__title">Warnings</p>
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
          Something went wrong
        </h3>
        <p className="failure__message">{hint ?? error?.message ?? "The service gave no reason."}</p>
        {error?.stage ? (
          <p className="muted">Stopped while {step ? RUN_STATUS_META[step].label.toLowerCase() : error.stage}.</p>
        ) : null}
        <p>{editorHoldsInput ? "Your code is still in the editor." : "Your code is saved with this run."}</p>
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
      <DetailsDrawer>
        {error ? (
          <p className="failure__code">
            Error code <code className="code-tag">{error.code}</code>: {error.message}
          </p>
        ) : null}
        {record.verification ? <ReasonList reasons={record.verification.disposition_reasons} /> : null}
        <WarningsNotice warnings={record.warnings} />
        <div className="result-section">
          <CodeListing title="Your code" code={record.original_code} findings={record.findings} />
        </div>
        {record.findings.length > 0 || record.analysis ? <AnalysisSection record={record} /> : null}
        <RunDetails record={record} />
      </DetailsDrawer>
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
      {record.verification ? (
        <CheckRow verification={record.verification} mode={record.workflow_mode} fake={fake} />
      ) : null}
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
          <p className="muted">{disposition === "no_change" ? "Your code stays as it is." : "No new code was made."}</p>
          <CodeListing title="Your code" code={record.original_code} findings={record.findings} />
        </div>
      )}
      {proposal ? (
        <DecisionPanel
          decision={record.human_decision}
          disposition={disposition}
          state={decision}
          onDecide={(choice) => onDecide(record.run_id, choice)}
        />
      ) : null}
      <DetailsDrawer>
        {proposal && record.proposed_code !== null ? (
          <ShapeComparison original={record.original_code} proposed={record.proposed_code} />
        ) : null}
        {record.verification && record.verification.disposition_reasons.length > 0 ? (
          <div className="result-section">
            <h3 className="result-section__title">Why</h3>
            <ReasonList reasons={record.verification.disposition_reasons} />
          </div>
        ) : null}
        <WarningsNotice warnings={record.warnings} />
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
        <RunDetails record={record} />
      </DetailsDrawer>
    </>
  );
}
