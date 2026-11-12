import { useMemo } from 'react';

import { useRunHistory, useStats } from '@/entities/queries';
import { formatDuration, formatTokens, shortId } from '@/shared/lib/format';
import { Badge } from '@/shared/ui/Feedback';
import { Spinner } from '@/shared/ui/Button';

/**
 * Measured aggregates over the run history.
 *
 * Every number comes from `GET /api/v1/stats`, which computes them from the
 * stored run records; the chart below plots the same records. Nothing here is
 * estimated — when the service reports a truncated sample the panel says so.
 */
export function InsightsPanel() {
  const stats = useStats();
  const history = useRunHistory(50);

  const recent = useMemo(() => (history.data ?? []).slice(0, 12).reverse(), [history.data]);
  const maxDuration = useMemo(
    () => Math.max(1, ...recent.map((run) => Number(run.metrics.total_duration_ms ?? 0))),
    [recent],
  );

  if (stats.isLoading) {
    return (
      <div className="flex items-center gap-2 px-3 py-3 text-xs text-fg-subtle">
        <Spinner size={13} />
        Loading the measured aggregates…
      </div>
    );
  }

  if (!stats.data) {
    return (
      <p className="px-3 py-3 text-xs text-fg-subtle">
        The aggregates are unavailable while the API is unreachable.
      </p>
    );
  }

  const data = stats.data;

  return (
    <div className="flex flex-col gap-2 border-b border-edge px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
        <span className="text-fg-muted">
          runs <span className="font-mono text-fg">{data.total_runs}</span>
        </span>
        <span className="text-fg-muted">
          approved{' '}
          <span className="font-mono text-fg">
            {data.acceptance_rate === null ? '—' : `${(data.acceptance_rate * 100).toFixed(0)}%`}
          </span>
        </span>
        <span className="text-fg-muted">
          mean duration{' '}
          <span className="font-mono text-fg">{formatDuration(data.mean_duration_ms)}</span>
        </span>
        <span className="text-fg-muted">
          mean tokens{' '}
          <span className="font-mono text-fg">{formatTokens(data.mean_total_tokens)}</span>
        </span>
        <span className="text-fg-muted">
          in flight <span className="font-mono text-fg">{data.runs_in_flight}</span>
        </span>
        {data.truncated ? (
          <Badge tone="warning" title="The aggregate covers only the most recent runs.">
            sampled {data.sampled_runs}
          </Badge>
        ) : null}
      </div>

      {recent.length > 0 ? (
        <div className="flex items-end gap-1" role="img" aria-label="Duration of the most recent runs">
          {recent.map((run) => {
            const duration = Number(run.metrics.total_duration_ms ?? 0);
            const height = Math.max(6, Math.round((duration / maxDuration) * 34));
            const verdict = run.verification?.review_verdict ?? 'pending';
            const tone =
              verdict === 'approved'
                ? 'bg-success'
                : verdict === 'rejected'
                  ? 'bg-danger'
                  : 'bg-fg-subtle';
            return (
              <span
                key={run.id}
                title={`${shortId(run.id)} · ${verdict} · ${formatDuration(duration)}`}
                className={`w-2.5 rounded-sm ${tone}`}
                style={{ height }}
              />
            );
          })}
          <span className="ml-1 text-[10px] text-fg-subtle">
            last {recent.length} run(s) by duration
          </span>
        </div>
      ) : null}
    </div>
  );
}
