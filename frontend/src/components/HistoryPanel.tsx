import { type RefObject, useId, useState } from "react";
import { type ApiError, toApiError } from "../api/client";
import { RUN_LIST_MAX_LIMIT, type RunSummary } from "../api/contracts";
import { formatDateTime, shortId } from "../lib/format";
import { DISPOSITION_META, type IconName, RUN_STATUS_META, type Tone, WORKFLOW_META } from "../lib/labels";
import { Icon } from "./Icon";
import { StatusBadge } from "./StatusBadge";

interface HistoryPanelProps {
  runs: RunSummary[] | null;
  limit: number;
  loading: boolean;
  error: ApiError | null;
  selectedId: string | null;
  headingRef: RefObject<HTMLHeadingElement | null>;
  onRefresh: () => void;
  onShowMore: () => void;
  onOpen: (runId: string) => void;
  onDelete: (runId: string) => Promise<void>;
}

const STATUS_ICON: Record<string, IconName> = {
  queued: "clock",
  analyzing: "spinner",
  generating: "spinner",
  verifying: "spinner",
  failed: "cross",
  completed: "check",
};

function RunChips({ run }: { run: RunSummary }) {
  // A completed run is described by its disposition; other runs by their status.
  const showDisposition = run.status === "completed" && run.disposition !== null;
  const statusMeta = RUN_STATUS_META[run.status];
  const tone: Tone = statusMeta.tone;
  return (
    <span className="chips">
      {showDisposition && run.disposition ? (
        <StatusBadge
          meta={{
            label: DISPOSITION_META[run.disposition].label,
            tone: DISPOSITION_META[run.disposition].tone,
            icon: DISPOSITION_META[run.disposition].icon,
          }}
          hiddenPrefix="Completed:"
        />
      ) : (
        <StatusBadge meta={{ label: statusMeta.label, tone, icon: STATUS_ICON[run.status] ?? "dash" }} />
      )}
      {run.provider_mode === "fake" ? <span className="tag tag--fake">Fake</span> : null}
      {run.human_decision ? (
        <span className="tag">{run.human_decision === "accepted" ? "Accepted by you" : "Rejected by you"}</span>
      ) : null}
    </span>
  );
}

function HistoryItem({
  run,
  selected,
  onOpen,
  onDelete,
}: {
  run: RunSummary;
  selected: boolean;
  onOpen: (runId: string) => void;
  onDelete: (runId: string) => Promise<void>;
}) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const when = formatDateTime(run.created_at);

  const confirmDelete = async () => {
    setDeleting(true);
    setError(null);
    try {
      await onDelete(run.run_id);
    } catch (caught) {
      setError(toApiError(caught));
      setDeleting(false);
    }
  };

  return (
    <li className="history-item" data-selected={selected ? "true" : undefined} aria-current={selected ? "true" : undefined}>
      <div className="history-item__main">
        <p className="history-item__when">
          <time dateTime={run.created_at}>{when}</time>
        </p>
        <RunChips run={run} />
        <p className="history-item__meta">
          {WORKFLOW_META[run.workflow_mode].label}
          {run.reference_case_id ? (
            <>
              , case <span className="mono">{run.reference_case_id}</span>
            </>
          ) : (
            ", no reference case"
          )}
          , run <span className="mono">{shortId(run.run_id)}</span>
        </p>
      </div>
      {confirming ? (
        <div className="history-item__confirm" role="group" aria-label={`Confirm deleting the run from ${when}`}>
          <p>Delete this run and its stored record? This cannot be undone.</p>
          <div className="history-item__actions">
            <button
              type="button"
              className="button button--small"
              data-variant="danger"
              onClick={() => void confirmDelete()}
              disabled={deleting}
            >
              {deleting ? "Deleting…" : "Delete run"}
            </button>
            <button
              type="button"
              className="button button--small button--quiet"
              onClick={() => {
                setConfirming(false);
                setError(null);
              }}
              disabled={deleting}
            >
              Keep run
            </button>
          </div>
        </div>
      ) : (
        <div className="history-item__actions">
          <button
            type="button"
            className="button button--small"
            onClick={() => onOpen(run.run_id)}
            aria-label={`Open the run from ${when}`}
          >
            Open
          </button>
          <button
            type="button"
            className="button button--small button--quiet"
            onClick={() => setConfirming(true)}
            aria-label={`Delete the run from ${when}`}
          >
            <Icon name="trash" />
            Delete
          </button>
        </div>
      )}
      {error ? (
        <p className="field-message" data-tone="fail" role="alert">
          The run was not deleted: {error.message}
        </p>
      ) : null}
    </li>
  );
}

export function HistoryPanel({
  runs,
  limit,
  loading,
  error,
  selectedId,
  headingRef,
  onRefresh,
  onShowMore,
  onOpen,
  onDelete,
}: HistoryPanelProps) {
  const ids = useId();
  const canShowMore = runs !== null && runs.length >= limit && limit < RUN_LIST_MAX_LIMIT;
  return (
    <section className="panel history-panel" aria-labelledby={`${ids}-heading`}>
      <div className="panel__head panel__head--row">
        <div>
          <h2 id={`${ids}-heading`} ref={headingRef} tabIndex={-1}>
            History
          </h2>
          <p className="panel__sub">Runs stored on this machine, newest first</p>
        </div>
        <button type="button" className="button button--small button--quiet" onClick={onRefresh} disabled={loading}>
          <Icon name="refresh" />
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>
      {error ? (
        <p className="field-message" data-tone="fail" role="status">
          Could not load the history: {error.message}
        </p>
      ) : null}
      {runs === null ? (
        loading ? (
          <p className="loading">Loading the history…</p>
        ) : null
      ) : runs.length === 0 ? (
        <p className="muted">No runs yet. Submitted runs appear here.</p>
      ) : (
        <ol className="history-list">
          {runs.map((run) => (
            <HistoryItem
              key={run.run_id}
              run={run}
              selected={run.run_id === selectedId}
              onOpen={onOpen}
              onDelete={onDelete}
            />
          ))}
        </ol>
      )}
      {runs !== null && runs.length > 0 ? (
        <div className="history-foot">
          <p className="muted">
            Showing the {runs.length === 1 ? "only stored run" : `${runs.length} most recent runs`}.
          </p>
          {canShowMore ? (
            <button type="button" className="button button--small button--quiet" onClick={onShowMore}>
              Show up to {RUN_LIST_MAX_LIMIT}
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
